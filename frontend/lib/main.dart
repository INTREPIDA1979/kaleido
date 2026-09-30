import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:audioplayers/audioplayers.dart';

void main() {
  runApp(const KaleidoApp());
}

Color hexToColor(String? hexString, {Color fallback = const Color(0xFFF3E5F5)}) {
  if (hexString == null || hexString.isEmpty) return fallback;
  try {
    final buffer = StringBuffer();
    if (hexString.length == 6 || hexString.length == 7) buffer.write('ff');
    buffer.write(hexString.replaceFirst('#', ''));
    return Color(int.parse(buffer.toString(), radix: 16));
  } catch (e) {
    return fallback;
  }
}

Color getDarkerColor(Color baseColor) {
  HSLColor hsl = HSLColor.fromColor(baseColor);
  return hsl.withLightness(0.35).withSaturation((hsl.saturation + 0.2).clamp(0.0, 1.0)).toColor();
}

class KaleidoApp extends StatelessWidget {
  const KaleidoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kaleido',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFFAFAFA),
      ),
      home: const ChatScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class Message {
  final String text;
  final String role;
  final String? agentId;
  final String? agentName;
  final String? themeColor;

  Message({
    required this.text,
    required this.role,
    this.agentId,
    this.agentName,
    this.themeColor,
  });
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  List<Message> _messages = [];
  bool _isLoading = false;

  XFile? _selectedImage;
  final ImagePicker _picker = ImagePicker();

  late stt.SpeechToText _speech;
  late AudioPlayer _audioPlayer;
  bool _isListening = false;
  bool _isTtsEnabled = true;
  
  String _currentUserId = 'user_a';

  @override
  void initState() {
    super.initState();
    _speech = stt.SpeechToText();
    _audioPlayer = AudioPlayer();
    _fetchHistory(_currentUserId);
  }

  Future<void> _fetchHistory(String userId) async {
    setState(() {
      _isLoading = true;
      _messages.clear();
    });
    try {
      final response = await http.get(Uri.parse('http://127.0.0.1:8080/api/v1/history?user_id=$userId'));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        final List<dynamic> list = data['history'] ?? [];
        setState(() {
          _messages = list.map((e) => Message(
            text: e['text'] ?? '',
            role: e['role'] ?? 'user',
            agentId: e['agent_id'],
            agentName: e['agent_name'],
            themeColor: e['theme_color'],
          )).toList();
        });
        _scrollToBottom();
      }
    } catch (e) {
      print('履歴取得エラー: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _resetDemoData() async {
    setState(() {
      _isLoading = true;
      _messages.clear();
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('🔄 デモ環境を完全に初期化しています...（少し時間がかかります）')),
    );

    try {
      const String backendUrl = String.fromEnvironment('BACKEND_URL', defaultValue: 'http://127.0.0.1:8080');
      
      final response = await http.post(
        Uri.parse('$backendUrl/api/v1/reset'),
      );

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('✨ 初期化が完了しました！')),
        );
        await _fetchHistory(_currentUserId);
      } else {
        throw Exception('リセットに失敗しました');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('🚨 エラーが発生しました: $e')),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  void _listen() async {
    if (!_isListening) {
      bool available = await _speech.initialize(
        onStatus: (val) => print('onStatus: $val'),
        onError: (val) => print('onError: $val'),
      );
      if (available) {
        setState(() => _isListening = true);
        _speech.listen(
          onResult: (val) => setState(() {
            _controller.text = val.recognizedWords;
          }),
          localeId: 'ja_JP',
        );
      }
    } else {
      setState(() => _isListening = false);
      _speech.stop();
    }
  }

  Future<void> _pickImage() async {
    final XFile? image = await _picker.pickImage(source: ImageSource.gallery);
    if (image != null) {
      setState(() => _selectedImage = image);
    }
  }

  void _clearImage() {
    setState(() => _selectedImage = null);
  }

  Color _getAgentBgColor(String? agentId) {
    switch (agentId) {
      case 'travel_planner_01': return const Color(0xFFE0F7FA);
      case 'beauty_analyst_01': return const Color(0xFFFCE4EC);
      default: return const Color(0xFFF3E5F5);
    }
  }

  String _getFallbackAgentName(String? agentId) {
    if (agentId == 'travel_planner_01') return '駅すぱあと経路検索エージェント';
    if (agentId == 'beauty_analyst_01') return 'YouCam肌分析エージェント';
    return 'AIアシスタント';
  }

  Color _getAgentIconColor(String? agentId) {
    switch (agentId) {
      case 'travel_planner_01': return Colors.cyan.shade600;
      case 'beauty_analyst_01': return Colors.pink.shade400;
      default: return Colors.purple.shade500;
    }
  }

  IconData _getAgentIcon(String? agentId) {
    switch (agentId) {
      case 'travel_planner_01': return Icons.train;
      case 'beauty_analyst_01': return Icons.face_retouching_natural;
      default: return Icons.auto_awesome;
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty && _selectedImage == null) return;
    if (_isLoading) return;

    await _audioPlayer.stop();
    
    if (_isListening) {
      _speech.stop();
      setState(() => _isListening = false);
    }

    setState(() => _isLoading = true);

    String imageUrl = '';
    String displayMessage = text;

    if (_selectedImage != null) {
      try {
        displayMessage = text.isEmpty ? '[画像を送信しました]' : '[画像を送信しました]\n$text';
        final imageToUpload = _selectedImage!;
        setState(() {
          _messages.add(Message(text: displayMessage, role: 'user'));
          _selectedImage = null; 
        });
        _scrollToBottom();

        final uploadUrl = Uri.parse('http://127.0.0.1:8080/api/v1/upload');
        var request = http.MultipartRequest('POST', uploadUrl);
        final bytes = await imageToUpload.readAsBytes();
        request.files.add(http.MultipartFile.fromBytes('file', bytes, filename: imageToUpload.name));
        
        var streamedResponse = await request.send();
        var response = await http.Response.fromStream(streamedResponse);
        
        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);
          imageUrl = data['url'];
        } else {
          throw Exception('サーバーエラー (${response.statusCode})');
        }
      } catch (e) {
        setState(() {
          _messages.add(Message(text: '画像のアップロードに失敗しました: $e', role: 'agent'));
          _isLoading = false;
        });
        return;
      }
    } else {
      setState(() => _messages.add(Message(text: text, role: 'user')));
      _scrollToBottom();
    }

    _controller.clear();

    String prompt = text;
    if (imageUrl.isNotEmpty) {
      prompt = text.isEmpty ? '対象の画像URL: $imageUrl' : '$text\n\n対象の画像URL: $imageUrl';
    }

    try {
      final url = Uri.parse('http://127.0.0.1:8080/api/v1/chat');
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'user_id': _currentUserId,
          'message': prompt,
        }),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        final responseMessage = data['response_message'] ?? '';
        final voiceName = data['voice_name'] ?? 'ja-JP-Neural2-B';
        
        setState(() {
          _messages.add(Message(
            text: responseMessage,
            role: 'agent',
            agentId: data['agent_id'] ?? 'default',
            agentName: data['agent_name'] ?? 'AIアシスタント',
            themeColor: data['theme_color'],
          ));
        });

        if (_isTtsEnabled) {
          final cleanText = responseMessage.replaceAll(RegExp(r'[#*`_]'), '');
          final ttsResponse = await http.post(
            Uri.parse('http://127.0.0.1:8080/api/v1/tts'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'text': cleanText,
              'voice_name': voiceName,
            }),
          );

          if (ttsResponse.statusCode == 200) {
            final ttsData = jsonDecode(ttsResponse.body);
            final audioUrl = ttsData['audio_url'];
            await _audioPlayer.play(UrlSource(audioUrl));
          }
        }
      } else {
        setState(() => _messages.add(Message(text: 'サーバーエラーが発生しました (${response.statusCode})', role: 'agent')));
      }
    } catch (e) {
      setState(() => _messages.add(Message(text: '通信エラー: FastAPIサーバーが起動しているか確認してください。\n詳細: $e', role: 'agent')));
    } finally {
      setState(() => _isLoading = false);
      _scrollToBottom();
    }
  }

  Widget _buildMessageBubble(Message message) {
    bool isUser = message.role == 'user';

    if (isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(top: 12, bottom: 12, left: 50, right: 16),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 18),
          decoration: BoxDecoration(
            color: const Color(0xFFF0F0F0),
            borderRadius: BorderRadius.circular(20).copyWith(bottomRight: const Radius.circular(4)),
          ),
          child: SelectableText(
            message.text,
            style: const TextStyle(color: Colors.black87, fontSize: 15, height: 1.4),
          ),
        ),
      );
    } else {
      Color bgColor = message.themeColor != null 
          ? hexToColor(message.themeColor).withOpacity(0.6) 
          : _getAgentBgColor(message.agentId).withOpacity(0.6);

      Color accentColor = message.themeColor != null 
          ? getDarkerColor(bgColor)
          : _getAgentIconColor(message.agentId);

      return Container(
        width: double.infinity,
        color: bgColor,
        padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CircleAvatar(
              backgroundColor: Colors.white,
              radius: 18,
              child: Icon(_getAgentIcon(message.agentId), color: accentColor, size: 20),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    message.agentName ?? _getFallbackAgentName(message.agentId),
                    style: TextStyle(fontWeight: FontWeight.bold, color: accentColor, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  MarkdownBody(
                    data: message.text,
                    selectable: true,
                    styleSheet: MarkdownStyleSheet(
                      p: const TextStyle(fontSize: 15, height: 1.7, color: Colors.black87),
                      h3: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Colors.black87),
                      listBullet: const TextStyle(fontSize: 15, color: Colors.black87),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    }
  }

  Widget _buildMessageInput() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
      decoration: const BoxDecoration(
        color: Colors.white,
        boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, -1))],
      ),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_selectedImage != null)
              Container(
                margin: const EdgeInsets.only(bottom: 8.0, left: 48.0),
                padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
                decoration: BoxDecoration(color: Colors.grey[200], borderRadius: BorderRadius.circular(12)),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.image, color: Colors.blue, size: 20),
                    const SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        _selectedImage!.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 13, color: Colors.black87),
                      ),
                    ),
                    const SizedBox(width: 4),
                    InkWell(onTap: _clearImage, child: const Icon(Icons.close, size: 18, color: Colors.black54)),
                  ],
                ),
              ),
            Row(
              children: [
                IconButton(icon: const Icon(Icons.attach_file, color: Colors.grey), onPressed: _isLoading ? null : _pickImage),
                Expanded(
                  child: Focus(
                    onKeyEvent: (node, event) {
                      if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter) {
                        if (HardwareKeyboard.instance.isControlPressed || HardwareKeyboard.instance.isShiftPressed) {
                          return KeyEventResult.ignored;
                        } else {
                          if (!_isLoading) _sendMessage();
                          return KeyEventResult.handled;
                        }
                      }
                      return KeyEventResult.ignored;
                    },
                    child: TextField(
                      controller: _controller,
                      maxLines: 4,
                      minLines: 1,
                      decoration: InputDecoration(
                        hintText: _isListening ? 'マイクでお話しください...' : 'エージェントに相談するか、画像を添付...',
                        hintStyle: TextStyle(color: _isListening ? Colors.redAccent : Colors.grey[400]),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                        filled: true,
                        fillColor: const Color(0xFFF1F3F4),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                        suffixIcon: IconButton(
                          icon: Icon(
                            _isListening ? Icons.mic : Icons.mic_none,
                            color: _isListening ? Colors.red : Colors.grey,
                          ),
                          onPressed: _listen,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                CircleAvatar(
                  backgroundColor: _isLoading ? Colors.grey : Colors.black87,
                  radius: 22,
                  child: IconButton(icon: const Icon(Icons.send, color: Colors.white, size: 20), onPressed: _isLoading ? null : _sendMessage),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.blur_on, color: Colors.black87),
            SizedBox(width: 8),
            Text('Kaleido', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 22, letterSpacing: 1.2)),
          ],
        ),
        centerTitle: false,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        elevation: 0,
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4.0, vertical: 8.0),
            child: OutlinedButton.icon(
              icon: const Icon(Icons.delete_sweep, size: 16),
              label: const Text('環境リセット', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.red.shade400,
                side: BorderSide(color: Colors.red.shade400),
                padding: const EdgeInsets.symmetric(horizontal: 12),
              ),
              onPressed: () {
                showDialog(
                  context: context,
                  builder: (context) => AlertDialog(
                    title: const Text('環境の初期化'),
                    content: const Text('すべてのチャット履歴と生成されたエージェントを削除し、初期状態に戻しますか？'),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('キャンセル'),
                      ),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.red.shade400,
                          foregroundColor: Colors.white,
                        ),
                        onPressed: () {
                          Navigator.pop(context);
                          _resetDemoData();
                        },
                        child: const Text('リセット実行'),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(right: 8.0, left: 4.0),
            child: DropdownButton<String>(
              value: _currentUserId,
              icon: const Icon(Icons.person_outline, color: Colors.black87, size: 20),
              underline: const SizedBox(),
              style: const TextStyle(color: Colors.black87, fontSize: 13, fontWeight: FontWeight.bold),
              onChanged: (String? newValue) {
                if (newValue != null && newValue != _currentUserId) {
                  setState(() {
                    _currentUserId = newValue;
                  });
                  _audioPlayer.stop();
                  _fetchHistory(newValue);
                }
              },
              items: const [
                DropdownMenuItem(value: 'user_a', child: Text('User A (新規)')),
                DropdownMenuItem(value: 'user_b', child: Text('User B (既存)')),
              ],
            ),
          ),
          IconButton(
            icon: Icon(
              _isTtsEnabled ? Icons.volume_up : Icons.volume_off,
              color: _isTtsEnabled ? Colors.blue : Colors.grey,
            ),
            tooltip: _isTtsEnabled ? '音声読み上げ: オン' : '音声読み上げ: オフ',
            onPressed: () {
              setState(() {
                _isTtsEnabled = !_isTtsEnabled;
              });
              if (!_isTtsEnabled) {
                _audioPlayer.stop(); 
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.hub, color: Colors.black87),
            tooltip: 'エージェント相関図',
            onPressed: () {
              Navigator.push(context, MaterialPageRoute(builder: (_) => AgentsScreen(
                userId: _currentUserId, 
                chatMessages: _messages
              )));
            },
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              itemCount: _messages.length,
              itemBuilder: (context, index) => _buildMessageBubble(_messages[index]),
            ),
          ),
          if (_isLoading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                  SizedBox(width: 12),
                  Text('エージェントが思考中...', style: TextStyle(color: Colors.grey, fontSize: 13)),
                ],
              ),
            ),
          _buildMessageInput(),
        ],
      ),
    );
  }
}

class AgentInfo {
  final String id;
  final String name;
  final String description;
  final String themeColor;

  AgentInfo({
    required this.id,
    required this.name,
    required this.description,
    required this.themeColor,
  });

  factory AgentInfo.fromJson(Map<String, dynamic> json) {
    return AgentInfo(
      id: json['id'] ?? '',
      name: json['name'] ?? '名称未設定',
      description: json['description'] ?? '',
      themeColor: json['theme_color'] ?? '#F3E5F5',
    );
  }
}

class AgentsScreen extends StatefulWidget {
  final String userId; 
  final List<Message> chatMessages;
  
  const AgentsScreen({super.key, required this.userId, required this.chatMessages});

  @override
  State<AgentsScreen> createState() => _AgentsScreenState();
}

class _AgentsScreenState extends State<AgentsScreen> {
  List<AgentInfo> _agents = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchAgents();
  }

  Future<void> _fetchAgents() async {
    try {
      final response = await http.get(Uri.parse('http://127.0.0.1:8080/api/v1/agents?user_id=${widget.userId}'));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        final List<dynamic> list = data['agents'] ?? [];
        
        List<AgentInfo> fetchedAgents = list.map((e) => AgentInfo.fromJson(e)).toList();
        
        final existingIds = fetchedAgents.map((e) => e.id).toSet();
        
        for (var msg in widget.chatMessages) {
          if (msg.role == 'agent' && msg.agentId != null && msg.agentId != 'default' && msg.agentId != 'parse_error') {
            if (!existingIds.contains(msg.agentId)) {
               String fallbackName = 'AIアシスタント';
               String fallbackColor = '#F3E5F5';
               if (msg.agentId == 'travel_planner_01') { fallbackName = '駅すぱあと経路検索エージェント'; fallbackColor = '#E0F7FA'; }
               if (msg.agentId == 'beauty_analyst_01') { fallbackName = 'YouCam肌分析エージェント'; fallbackColor = '#FCE4EC'; }
               
               fetchedAgents.add(AgentInfo(
                 id: msg.agentId!,
                 name: msg.agentName ?? fallbackName,
                 description: '過去のチャットでサポートした専門家',
                 themeColor: msg.themeColor ?? fallbackColor,
               ));
               existingIds.add(msg.agentId!);
            }
          }
        }

        setState(() {
          _agents = fetchedAgents;
          _isLoading = false;
        });
      } else {
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('エージェント相関図', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        elevation: 1,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                Expanded(
                  flex: 3,
                  child: Container(
                    width: double.infinity,
                    color: const Color(0xFFFAFAFA),
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final width = constraints.maxWidth;
                        final height = constraints.maxHeight;
                        final center = Offset(width / 2, height / 2);
                        final radius = min(width, height) * 0.35;

                        return Stack(
                          children: [
                            CustomPaint(
                              size: Size(width, height),
                              painter: LinesPainter(
                                count: _agents.length,
                                center: center,
                                radius: radius,
                              ),
                            ),
                            Positioned(
                              left: center.dx - 35,
                              top: center.dy - 35,
                              child: Column(
                                children: [
                                  CircleAvatar(
                                    radius: 26,
                                    backgroundColor: widget.userId == 'user_a' ? Colors.black87 : Colors.indigo,
                                    child: const Icon(Icons.person, color: Colors.white, size: 28),
                                  ),
                                  const SizedBox(height: 4),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: widget.userId == 'user_a' ? Colors.black87 : Colors.indigo, 
                                      borderRadius: BorderRadius.circular(12)
                                    ),
                                    child: Text(
                                      widget.userId == 'user_a' ? 'User A' : 'User B',
                                      style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold)
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            ...List.generate(_agents.length, (index) {
                              final agent = _agents[index];
                              final angle = (2 * pi * index) / _agents.length - (pi / 2); 
                              final x = center.dx + radius * cos(angle);
                              final y = center.dy + radius * sin(angle);
                              
                              final bgColor = hexToColor(agent.themeColor);
                              final accentColor = getDarkerColor(bgColor);

                              return Positioned(
                                left: x - 40,
                                top: y - 40,
                                width: 80,
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    CircleAvatar(
                                      radius: 22,
                                      backgroundColor: bgColor.withOpacity(0.9),
                                      child: Icon(Icons.auto_awesome, color: accentColor, size: 20),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      agent.name,
                                      textAlign: TextAlign.center,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: accentColor),
                                    ),
                                  ],
                                ),
                              );
                            }),
                          ],
                        );
                      },
                    ),
                  ),
                ),
                const Divider(height: 1, color: Colors.black12),
                Expanded(
                  flex: 2,
                  child: Container(
                    color: Colors.white,
                    child: ListView.builder(
                      itemCount: _agents.length,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      itemBuilder: (context, index) {
                        final agent = _agents[index];
                        final bgColor = hexToColor(agent.themeColor);
                        final accentColor = getDarkerColor(bgColor);
                        
                        return Card(
                          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                          elevation: 0,
                          color: bgColor.withOpacity(0.3),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                            side: BorderSide(color: bgColor.withOpacity(0.6)),
                          ),
                          child: ListTile(
                            leading: CircleAvatar(
                              backgroundColor: Colors.white,
                              child: Icon(Icons.auto_awesome, color: accentColor),
                            ),
                            title: Text(agent.name, style: TextStyle(fontWeight: FontWeight.bold, color: accentColor, fontSize: 14)),
                            subtitle: Text(agent.description, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: Colors.black87)),
                          ),
                        );
                      },
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class LinesPainter extends CustomPainter {
  final int count;
  final Offset center;
  final double radius;

  LinesPainter({required this.count, required this.center, required this.radius});

  @override
  void paint(Canvas canvas, Size size) {
    if (count == 0) return;
    final paint = Paint()
      ..color = Colors.grey.shade300
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;

    for (int i = 0; i < count; i++) {
      final angle = (2 * pi * i) / count - (pi / 2);
      final x = center.dx + radius * cos(angle);
      final y = center.dy + radius * sin(angle);
      canvas.drawLine(center, Offset(x, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}