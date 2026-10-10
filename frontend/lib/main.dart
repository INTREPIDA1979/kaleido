import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:audioplayers/audioplayers.dart';

const String baseUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://127.0.0.1:8080',
);

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
  final String? avatarUrl;

  Message({
    required this.text,
    required this.role,
    this.agentId,
    this.agentName,
    this.themeColor,
    this.avatarUrl,
  });
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with TickerProviderStateMixin {
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
  bool _isVoiceOnlyMode = false;
  bool _isPlayingAudio = false;

  String _currentUserId = 'user_a';

  String? _currentSpeakingAvatarUrl;
  String? _currentSpeakingAgentName;
  Color? _currentSpeakingThemeColor;
  bool _showAvatar = false;

  late AnimationController _avatarAnimController;
  late Animation<double> _scaleAnimation;
  late Animation<Offset> _slideAnimation;
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _speech = stt.SpeechToText();
    _audioPlayer = AudioPlayer();

    _avatarAnimController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _scaleAnimation = CurvedAnimation(
      parent: _avatarAnimController,
      curve: Curves.elasticOut,
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0.2, -0.1),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _avatarAnimController,
      curve: Curves.easeOutBack,
    ));

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);

    _audioPlayer.onPlayerStateChanged.listen((state) {
      if (mounted) {
        setState(() {
          _isPlayingAudio = (state == PlayerState.playing);
        });
      }
    });

    _fetchHistory(_currentUserId);
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    _controller.dispose();
    _scrollController.dispose();
    _avatarAnimController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _fetchHistory(String userId) async {
    setState(() {
      _isLoading = true;
      _messages.clear();
      _showAvatar = false;
    });
    _avatarAnimController.reset();

    try {
      final response = await http.get(Uri.parse('$baseUrl/api/v1/history?user_id=$userId'));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        final List<dynamic> list = data['history'] ?? [];
        setState(() {
          _messages = list.map((e) {
            final rawRole = e['role'] ?? 'user';
            final normalizedRole = (rawRole == 'model' || rawRole == 'agent') ? 'agent' : 'user';

            // 💡 ユーザー発言に含まれる「対象の画像URL: ...」を正規表現で綺麗に除去
            String textContent = e['text'] ?? '';
            if (normalizedRole == 'user') {
              textContent = textContent
                  .replaceAll(RegExp(r'\n*対象の画像URL:\s*https?://\S+'), '')
                  .trim();
              if (textContent.isEmpty) {
                textContent = '[画像を送信しました]';
              }
            }

            return Message(
              text: textContent,
              role: normalizedRole,
              agentId: e['agent_id'],
              agentName: e['agent_name'],
              themeColor: e['theme_color'],
              avatarUrl: e['avatar_url'],
            );
          }).toList();

          final lastAgentMsg = _messages.lastWhere(
            (m) => m.role == 'agent' && m.avatarUrl != null && m.avatarUrl!.isNotEmpty,
            orElse: () => Message(text: '', role: 'user'),
          );
          if (lastAgentMsg.avatarUrl != null) {
            _currentSpeakingAvatarUrl = lastAgentMsg.avatarUrl;
            _currentSpeakingAgentName = lastAgentMsg.agentName;
            _currentSpeakingThemeColor = hexToColor(lastAgentMsg.themeColor);
            _showAvatar = true;
            _avatarAnimController.forward();
          }
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
      _showAvatar = false;
    });
    _avatarAnimController.reset();

    try {
      final response = await http.post(Uri.parse('$baseUrl/api/v1/reset'));
      if (response.statusCode == 200) {
        await _fetchHistory(_currentUserId);
      }
    } catch (e) {
      print('リセットエラー: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  void _listen() async {
    if (!_isListening) {
      _controller.clear();

      bool available = _speech.isAvailable;
      if (!available) {
        available = await _speech.initialize(
          onStatus: (status) {
            if (status == 'done' || status == 'notListening') {
              if (mounted && _isListening) {
                setState(() => _isListening = false);
                if (_isVoiceOnlyMode && _controller.text.trim().isNotEmpty) {
                  _sendMessage();
                }
              }
            }
          },
          onError: (errorNotification) {
            print('音声認識エラー: $errorNotification');
            if (mounted) {
              setState(() => _isListening = false);
            }
          },
        );
      }

      if (available) {
        setState(() => _isListening = true);
        await _speech.listen(
          onResult: (result) {
            if (!_isListening) return;

            setState(() {
              _controller.value = TextEditingValue(
                text: result.recognizedWords,
                selection: TextSelection.collapsed(offset: result.recognizedWords.length),
              );
            });
          },
          localeId: 'ja-JP',
          listenMode: stt.ListenMode.dictation,
          cancelOnError: true,
          partialResults: true,
        );
      }
    } else {
      await _speech.stop();
      setState(() => _isListening = false);

      if (_isVoiceOnlyMode) {
        if (_controller.text.trim().isNotEmpty) {
          _sendMessage();
        }
      }
    }
  }

  Future<void> _pickImage() async {
    final XFile? image = await _picker.pickImage(source: ImageSource.gallery);
    if (image != null) {
      setState(() => _selectedImage = image);
    }
  }

  void _clearImage() => setState(() => _selectedImage = null);

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

    if (_isListening) {
      await _speech.stop();
      setState(() => _isListening = false);
    }

    await _audioPlayer.stop();

    _controller.value = TextEditingValue.empty;
    _controller.clear();

    _avatarAnimController.reverse();

    setState(() {
      _isLoading = true;
      _showAvatar = false;
    });

    String imageUrl = '';
    String displayMessage = text.isEmpty ? '[画像を送信しました]' : text;

    if (_selectedImage != null) {
      try {
        final imageToUpload = _selectedImage!;
        setState(() {
          _messages.add(Message(text: displayMessage, role: 'user'));
          _selectedImage = null;
        });
        _scrollToBottom();

        final uploadUrl = Uri.parse('$baseUrl/api/v1/upload');
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

    String prompt = text;
    if (imageUrl.isNotEmpty) {
      prompt = text.isEmpty ? '対象の画像URL: $imageUrl' : '$text\n\n対象の画像URL: $imageUrl';
    }

    try {
      final url = Uri.parse('$baseUrl/api/v1/chat');
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
        final avatarUrl = data['avatar_url'];
        final agentName = data['agent_name'] ?? 'AIアシスタント';
        final themeColorHex = data['theme_color'];

        setState(() {
          _messages.add(Message(
            text: responseMessage,
            role: 'agent',
            agentId: data['agent_id'] ?? 'default',
            agentName: agentName,
            themeColor: themeColorHex,
            avatarUrl: avatarUrl,
          ));

          if (avatarUrl != null && avatarUrl.toString().isNotEmpty) {
            _currentSpeakingAvatarUrl = avatarUrl;
            _currentSpeakingAgentName = agentName;
            _currentSpeakingThemeColor = hexToColor(themeColorHex);
            _showAvatar = true;
          }
        });

        if (_showAvatar) {
          _avatarAnimController.forward(from: 0.0);
        }

        if (_isTtsEnabled) {
          final cleanText = responseMessage.replaceAll(RegExp(r'[#*`_]'), '');
          final ttsResponse = await http.post(
            Uri.parse('$baseUrl/api/v1/tts'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'text': cleanText, 'voice_name': voiceName}),
          );
          if (ttsResponse.statusCode == 200) {
            final ttsData = jsonDecode(ttsResponse.body);
            await _audioPlayer.play(UrlSource(ttsData['audio_url']));
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

  Widget _buildAvatarIcon({required String? avatarUrl, required String? agentId, required Color accentColor, double radius = 20}) {
    final hasAvatar = avatarUrl != null && avatarUrl.isNotEmpty;

    return Container(
      width: radius * 2,
      height: radius * 2,
      decoration: const BoxDecoration(
        shape: BoxShape.circle,
        color: Colors.white,
        boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 2, offset: Offset(0, 1))],
      ),
      child: ClipOval(
        child: hasAvatar
            ? Transform.scale(
                scale: 2.2,
                alignment: const Alignment(0.0, -0.65),
                child: Image.network(
                  avatarUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) =>
                      Center(child: Icon(_getAgentIcon(agentId), color: accentColor, size: radius)),
                ),
              )
            : Center(child: Icon(_getAgentIcon(agentId), color: accentColor, size: radius)),
      ),
    );
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
        padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildAvatarIcon(
              avatarUrl: message.avatarUrl,
              agentId: message.agentId,
              accentColor: accentColor,
              radius: 20,
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    message.agentName ?? _getFallbackAgentName(message.agentId),
                    style: TextStyle(fontWeight: FontWeight.bold, color: accentColor, fontSize: 14),
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

  // 💡 音声対話特化モード（画像添付ボタンを確実に画面下部中央へ常時表示）
  Widget _buildVoiceOnlyView() {
    final hasAvatar = _currentSpeakingAvatarUrl != null && _currentSpeakingAvatarUrl!.isNotEmpty;
    final agentName = _currentSpeakingAgentName ?? 'AIアシスタント';
    final themeColor = _currentSpeakingThemeColor ?? const Color(0xFFCE93D8);

    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            themeColor.withOpacity(0.15),
            Colors.white,
          ],
        ),
      ),
      child: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 10),

            // 1. ステータステキスト（何でも気軽にお話しください）
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: Container(
                key: ValueKey<String>('$_isLoading$_isPlayingAudio$_isListening'),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
                decoration: BoxDecoration(
                  color: themeColor.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  _isLoading
                      ? '⚡ 回答を考えています...'
                      : (_isPlayingAudio
                          ? '🗣️ $agentName が回答中'
                          : (_isListening ? '🎙️ お話しください...' : '何でも気軽にお話しください')),
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: getDarkerColor(themeColor),
                    letterSpacing: 0.5,
                  ),
                ),
              ),
            ),

            const SizedBox(height: 8),

            // 2. 担当エージェントの名前バッジ
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.9),
                borderRadius: BorderRadius.circular(20),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.06),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: getDarkerColor(themeColor),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '担当: $agentName',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      color: getDarkerColor(themeColor),
                    ),
                  ),
                ],
              ),
            ),

            // 3. アバター画像（中央エリア）
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 8.0),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final maxW = constraints.maxWidth;
                    final maxH = constraints.maxHeight;

                    return Center(
                      child: SizedBox(
                        width: maxW,
                        height: maxH,
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            if (_isPlayingAudio) ...[
                              AnimatedBuilder(
                                animation: _pulseController,
                                builder: (context, child) {
                                  return Container(
                                    width: (maxW * 0.85) + (_pulseController.value * 50),
                                    height: (maxH * 0.9) + (_pulseController.value * 50),
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(36),
                                      border: Border.all(
                                        color: themeColor.withOpacity((1.0 - _pulseController.value) * 0.4),
                                        width: 3,
                                      ),
                                    ),
                                  );
                                },
                              ),
                              AnimatedBuilder(
                                animation: _pulseController,
                                builder: (context, child) {
                                  final val = (_pulseController.value + 0.5) % 1.0;
                                  return Container(
                                    width: (maxW * 0.8) + (val * 40),
                                    height: (maxH * 0.85) + (val * 40),
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(32),
                                      border: Border.all(
                                        color: themeColor.withOpacity((1.0 - val) * 0.3),
                                        width: 2,
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ],

                            AnimatedBuilder(
                              animation: _pulseController,
                              builder: (context, child) {
                                final bounce = _isPlayingAudio ? sin(_pulseController.value * pi) * 6.0 : 0.0;
                                final scale = _isPlayingAudio ? 1.0 + (_pulseController.value * 0.02) : 1.0;

                                return Transform.translate(
                                  offset: Offset(0, -bounce),
                                  child: Transform.scale(
                                    scale: scale,
                                    child: Container(
                                      constraints: BoxConstraints(
                                        maxWidth: maxW * 0.9,
                                        maxHeight: maxH * 0.95,
                                      ),
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(28),
                                        boxShadow: [
                                          BoxShadow(
                                            color: themeColor.withOpacity(_isPlayingAudio ? 0.45 : 0.18),
                                            blurRadius: _isPlayingAudio ? 32 : 18,
                                            spreadRadius: _isPlayingAudio ? 6 : 2,
                                            offset: const Offset(0, 8),
                                          ),
                                        ],
                                      ),
                                      child: ClipRRect(
                                        borderRadius: BorderRadius.circular(28),
                                        child: hasAvatar
                                            ? Image.network(
                                                _currentSpeakingAvatarUrl!,
                                                fit: BoxFit.contain,
                                              )
                                            : Center(
                                                child: Icon(Icons.account_circle, size: 140, color: Colors.grey.shade400),
                                              ),
                                      ),
                                    ),
                                  ),
                                );
                              },
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),

            // 4. 音声再生中のイコライザー波形
            if (_isPlayingAudio)
              Padding(
                padding: const EdgeInsets.only(bottom: 6.0),
                child: AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    return Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: List.generate(5, (index) {
                        final wave = sin((_pulseController.value * 2 * pi) + (index * 0.8)).abs();
                        return Container(
                          margin: const EdgeInsets.symmetric(horizontal: 3),
                          width: 4,
                          height: 8 + (wave * 20),
                          decoration: BoxDecoration(
                            color: getDarkerColor(themeColor).withOpacity(0.7),
                            borderRadius: BorderRadius.circular(4),
                          ),
                        );
                      }),
                    );
                  },
                ),
              ),

            // 💡 添付された画像のプレビューチップ
            if (_selectedImage != null)
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 4.0),
                padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 6.0),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.95),
                  borderRadius: BorderRadius.circular(20),
                  boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 4)],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.image, color: Colors.blue, size: 18),
                    const SizedBox(width: 8),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 180),
                      child: Text(
                        _selectedImage!.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 13, color: Colors.black87),
                      ),
                    ),
                    const SizedBox(width: 6),
                    InkWell(
                      onTap: _clearImage,
                      child: const Icon(Icons.close, size: 18, color: Colors.black54),
                    ),
                  ],
                ),
              ),

            // 音声認識中テキストプレビュー
            if (_controller.text.isNotEmpty && _isListening)
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 4.0),
                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.92),
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 8)],
                ),
                child: Text(
                  _controller.text,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 15, color: Colors.black87, fontWeight: FontWeight.w500),
                ),
              ),

            // 💡 5. 最下部固定操作エリア（画像添付ボタン ＋ マイク ＋ 送信ボタン）
            Container(
              padding: const EdgeInsets.only(bottom: 24.0, top: 8.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  // 📷 画像添付ボタン（大きく見やすい丸ボタン）
                  Container(
                    width: 58,
                    height: 58,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.white,
                      border: Border.all(color: Colors.black12, width: 1.5),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.1),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: IconButton(
                      icon: Icon(
                        _selectedImage != null ? Icons.check_circle : Icons.add_photo_alternate,
                        color: _selectedImage != null ? Colors.blueAccent : Colors.black87,
                        size: 30,
                      ),
                      tooltip: '画像を添付',
                      onPressed: _isLoading ? null : _pickImage,
                    ),
                  ),

                  const SizedBox(width: 24),

                  // 🎙️ メインマイクボタン
                  GestureDetector(
                    onTap: _isLoading ? null : _listen,
                    child: AnimatedBuilder(
                      animation: _pulseController,
                      builder: (context, child) {
                        final scale = _isListening ? 1.0 + (_pulseController.value * 0.12) : 1.0;
                        return Transform.scale(
                          scale: scale,
                          child: Container(
                            width: 80,
                            height: 80,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: _isListening ? Colors.redAccent : Colors.black87,
                              boxShadow: [
                                BoxShadow(
                                  color: (_isListening ? Colors.redAccent : Colors.black).withOpacity(0.35),
                                  blurRadius: 20,
                                  offset: const Offset(0, 8),
                                ),
                              ],
                            ),
                            child: Icon(
                              _isListening ? Icons.mic : Icons.mic_none,
                              color: Colors.white,
                              size: 40,
                            ),
                          ),
                        );
                      },
                    ),
                  ),

                  const SizedBox(width: 24),

                  // 🚀 送信ボタン（画像がある場合は表示、なければ左右対称維持用のスペース）
                  if (_selectedImage != null)
                    Container(
                      width: 58,
                      height: 58,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.blueAccent,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.blueAccent.withOpacity(0.35),
                            blurRadius: 10,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: IconButton(
                        icon: const Icon(Icons.send, color: Colors.white, size: 26),
                        tooltip: '送信',
                        onPressed: _isLoading ? null : _sendMessage,
                      ),
                    )
                  else
                    const SizedBox(width: 58, height: 58),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final themeColor = _currentSpeakingThemeColor ?? const Color(0xFFF3E5F5);

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
                padding: const EdgeInsets.symmetric(horizontal: 10),
              ),
              onPressed: () {
                showDialog(
                  context: context,
                  builder: (context) => AlertDialog(
                    title: const Text('環境の初期化'),
                    content: const Text('すべてのチャット履歴と生成されたエージェントを削除し、初期状態に戻しますか？'),
                    actions: [
                      TextButton(onPressed: () => Navigator.pop(context), child: const Text('キャンセル')),
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
            padding: const EdgeInsets.only(right: 4.0, left: 4.0),
            child: DropdownButton<String>(
              value: _currentUserId,
              icon: const Icon(Icons.person_outline, color: Colors.black87, size: 20),
              underline: const SizedBox(),
              style: const TextStyle(color: Colors.black87, fontSize: 13, fontWeight: FontWeight.bold),
              onChanged: (String? newValue) {
                if (newValue != null && newValue != _currentUserId) {
                  setState(() => _currentUserId = newValue);
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
              _isVoiceOnlyMode ? Icons.chat_bubble_outline : Icons.headphones,
              color: _isVoiceOnlyMode ? Colors.purple : Colors.black87,
            ),
            tooltip: _isVoiceOnlyMode ? 'テキストチャットモードに切替' : '音声対話モードに切替',
            onPressed: () {
              if (_isListening) {
                _speech.stop();
              }
              _controller.clear();

              setState(() {
                _isVoiceOnlyMode = !_isVoiceOnlyMode;
                _isListening = false;
              });
            },
          ),
          IconButton(
            icon: Icon(
              _isTtsEnabled ? Icons.volume_up : Icons.volume_off,
              color: _isTtsEnabled ? Colors.blue : Colors.grey,
            ),
            tooltip: _isTtsEnabled ? '音声読み上げ: オン' : '音声読み上げ: オフ',
            onPressed: () {
              setState(() => _isTtsEnabled = !_isTtsEnabled);
              if (!_isTtsEnabled) _audioPlayer.stop();
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
      body: _isVoiceOnlyMode
          ? _buildVoiceOnlyView()
          : Stack(
              children: [
                Column(
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
                if (_currentSpeakingAvatarUrl != null)
                  Positioned(
                    top: 16,
                    right: 16,
                    child: IgnorePointer(
                      child: SlideTransition(
                        position: _slideAnimation,
                        child: ScaleTransition(
                          scale: _scaleAnimation,
                          child: AnimatedBuilder(
                            animation: _pulseController,
                            builder: (context, child) {
                              final glowIntensity = _isPlayingAudio ? _pulseController.value : 0.0;
                              return Container(
                                height: 230,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(16),
                                  boxShadow: [
                                    BoxShadow(
                                      color: themeColor.withOpacity(0.25 + (glowIntensity * 0.4)),
                                      blurRadius: 18 + (glowIntensity * 14),
                                      spreadRadius: 2 + (glowIntensity * 4),
                                    ),
                                    BoxShadow(
                                      color: Colors.black.withOpacity(0.12),
                                      blurRadius: 14,
                                      offset: const Offset(0, 4),
                                    ),
                                  ],
                                ),
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(16),
                                  child: Image.network(
                                    _currentSpeakingAvatarUrl!,
                                    fit: BoxFit.contain,
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                    ),
                  ),
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
  final String? avatarUrl;

  AgentInfo({
    required this.id,
    required this.name,
    required this.description,
    required this.themeColor,
    this.avatarUrl,
  });

  factory AgentInfo.fromJson(Map<String, dynamic> json) {
    return AgentInfo(
      id: json['id'] ?? json['agent_id'] ?? '',
      name: json['name'] ?? '名称未設定',
      description: json['description'] ?? '',
      themeColor: json['theme_color'] ?? '#F3E5F5',
      avatarUrl: json['avatar_url'],
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
      final response = await http.get(Uri.parse('$baseUrl/api/v1/agents?user_id=${widget.userId}'));
      List<AgentInfo> fetchedAgents = [];
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        final List<dynamic> list = data['agents'] ?? [];
        fetchedAgents = list.map((e) => AgentInfo.fromJson(e)).toList();
      }

      final existingIds = fetchedAgents.map((e) => e.id).toSet();
      for (var msg in widget.chatMessages) {
        if (msg.role == 'agent' && msg.agentId != null && !existingIds.contains(msg.agentId)) {
          fetchedAgents.add(AgentInfo(
            id: msg.agentId!,
            name: msg.agentName ?? 'AIアシスタント',
            description: '会話ログにある専門家',
            themeColor: msg.themeColor ?? '#F3E5F5',
            avatarUrl: msg.avatarUrl,
          ));
          existingIds.add(msg.agentId!);
        }
      }

      setState(() {
        _agents = fetchedAgents;
        _isLoading = false;
      });
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
                            painter: LinesPainter(count: _agents.length, center: center, radius: radius),
                          ),
                          Positioned(
                            left: center.dx - 30,
                            top: center.dy - 30,
                            child: CircleAvatar(
                              radius: 26,
                              backgroundColor: Colors.black87,
                              child: const Icon(Icons.person, color: Colors.white, size: 28),
                            ),
                          ),
                          ...List.generate(_agents.length, (index) {
                            final agent = _agents[index];
                            final angle = (2 * pi * index) / max(_agents.length, 1) - (pi / 2);
                            final x = center.dx + radius * cos(angle);
                            final y = center.dy + radius * sin(angle);
                            final hasAvatar = agent.avatarUrl != null && agent.avatarUrl!.isNotEmpty;

                            return Positioned(
                              left: x - 35,
                              top: y - 35,
                              width: 70,
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Container(
                                    width: 44,
                                    height: 44,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: hexToColor(agent.themeColor),
                                      boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 4)],
                                    ),
                                    child: ClipOval(
                                      child: hasAvatar
                                          ? Transform.scale(
                                              scale: 2.2,
                                              alignment: const Alignment(0.0, -0.65),
                                              child: Image.network(agent.avatarUrl!, fit: BoxFit.cover),
                                            )
                                          : const Icon(Icons.auto_awesome, color: Colors.black54, size: 20),
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    agent.name,
                                    textAlign: TextAlign.center,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold),
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
                const Divider(height: 1),
                Expanded(
                  flex: 2,
                  child: ListView.builder(
                    itemCount: _agents.length,
                    itemBuilder: (context, index) {
                      final agent = _agents[index];
                      final hasAvatar = agent.avatarUrl != null && agent.avatarUrl!.isNotEmpty;

                      return ListTile(
                        leading: Container(
                          width: 40,
                          height: 40,
                          decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white),
                          child: ClipOval(
                            child: hasAvatar
                                ? Transform.scale(
                                    scale: 2.2,
                                    alignment: const Alignment(0.0, -0.65),
                                    child: Image.network(agent.avatarUrl!, fit: BoxFit.cover),
                                  )
                                : const Icon(Icons.auto_awesome, color: Colors.grey),
                          ),
                        ),
                        title: Text(agent.name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                        subtitle: Text(agent.description, maxLines: 1, overflow: TextOverflow.ellipsis),
                      );
                    },
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