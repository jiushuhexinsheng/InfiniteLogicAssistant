/**
 * 离线语音唤醒模块 — Vosk-browser (WASM)
 *
 * 用 KaldiRecognizer 事件监听 partialresult/result 实现实时唤醒词检测。
 * acceptWaveform(AudioBuffer) → Worker 自动读取 sampleRate。
 * partialresult 由 Worker 主动推送，不需要手动调 retrieveFinalResult。
 */
var WakeWordEngine = (function () {
  'use strict';

  var _model = null;
  var _recognizer = null;
  var _audioCtx = null;
  var _scriptNode = null;
  var _stream = null;
  var _running = false;
  var _wakeCallback = null;
  var _stateCallback = null;
  var _latestPartial = '';
  var _chunkCount = 0;
  var _recognizerRate = 16000;

  // 支持**多个**唤醒词：命中任意一个即唤醒（配置见 voice.wake_word.keywords）。
  // Multiple wake keywords: a hit on any one of them wakes the engine.
  var _keywords = ['衍衡', '洛吉斯'];
  var _sensitivity = 0.3;       // 降低阈值以匹配更多发音变体
  var _modelPath = '/models/vosk-model-small-cn-0.22.tar.gz';
  var _modelLoaded = false;
  var _muteGain = null;         // 静音路由节点：保持 audio graph 活跃但不回放麦克风

  async function init(config) {
    config = config || {};
    _modelPath = config.modelPath || _modelPath;
    // 优先取数组 `keywords`；同时兼容旧的单数 `keyword`（老配置/老调用方不静默失效）。
    // Prefer the `keywords` array, while still honouring a legacy singular `keyword` so older
    // configs or callers do not silently stop working.
    if (config.keywords && config.keywords.length) {
      _keywords = config.keywords.slice();
    } else if (config.keyword) {
      _keywords = [config.keyword];
    }
    _sensitivity = (config.sensitivity != null) ? config.sensitivity : 0.3;
    console.log('[WW] init keywords=' + _keywords.join(' / '));

    if (typeof vosk === 'undefined') { console.warn('[WW] vosk missing'); return false; }
    if (_modelLoaded) return true;

    try {
      // vosk.js worker 只支持按 URL 加载（load() 内 modelUrl.replace），不支持字节
      _model = await vosk.createModel(_modelPath);
      _modelLoaded = true;
      console.log('[WW] model ready=' + _model.ready);
      return true;
    } catch (e) { console.error('[WW] model fail:', e); return false; }
  }

  function _newRecognizer() {
    if (!_model || !_model.ready) return null;
    var r = new _model.KaldiRecognizer(_recognizerRate);
    r.setWords(true);

    r.on('partialresult', function (msg) {
      if (!_running) return;
      var text = (msg && msg.result && msg.result.partial) || '';
      if (!text) return;
      _latestPartial = text;
      console.log('[WW] partial:' + text);
      if (_stateCallback) _stateCallback({ rms: 0, partial: text });
      if (match(text)) {
        console.log('[WW] WAKE! (partial) ' + text);
        _fireWake();
        _latestPartial = '';
        _destroyRec();
        _recognizer = _newRecognizer();
      }
    });

    r.on('result', function (msg) {
      if (!_running) return;
      var text = (msg && msg.result && msg.result.text) || '';
      if (!text) return;
      console.log('[WW] result:' + text);
      if (match(text)) {
        console.log('[WW] WAKE! (final) ' + text);
        _fireWake();
      }
    });

    return r;
  }

  function _destroyRec() {
    if (_recognizer) { try { _recognizer.remove(); } catch (e) {} _recognizer = null; }
  }

  // 唤醒命中后的统一出口。回调缺失时**必须留下可见痕迹** —— 这条路径上的静默失败
  // 曾经表现为「唤醒词明明识别到了，应用却毫无反应」，极难定位。
  // The single exit point for a wake hit. A missing callback **must leave a visible trace**:
  // a silent failure on this path once presented as "the wake word is clearly recognized but
  // the app does nothing", which is very hard to diagnose.
  function _fireWake() {
    if (_wakeCallback) { _wakeCallback(); return; }
    console.warn('[WW] 唤醒命中但没有唤醒回调 —— 应用层收不到本次唤醒（引擎是否被无参 start() 重启过？）');
  }

  async function start(onWake, onState) {
    if (!_modelLoaded) { console.error('[WW] no model'); return false; }
    if (_running) return true;
    // 只在**显式传入**时替换回调。start() 的契约是「重建流与 recognizer」，
    // 不传参即代表「沿用上次注册的回调」—— 恢复监听（播报结束）正是这么调的。
    // 若在此无条件赋 null，引擎照旧识别并打印 [WW] WAKE!，应用层却收不到唤醒回调，
    // 表现为「第一次唤醒能用，之后再也唤不醒」的静默失败。
    // Only replace the callbacks when explicitly provided: start()'s contract is "rebuild the
    // stream and recognizer", so omitting them means "keep the ones registered earlier" —
    // which is exactly how listening is resumed after playback. Unconditionally assigning null
    // here would leave the engine recognizing (and even logging [WW] WAKE!) while the app never
    // receives the callback: a silent failure presenting as "the first wake works, later ones
    // never do".
    if (onWake) _wakeCallback = onWake;
    if (onState) _stateCallback = onState;
    _latestPartial = '';
    _chunkCount = 0;

    try {
      _stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
      });
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      _recognizerRate = _audioCtx.sampleRate;
      console.log('[WW] rate=' + _recognizerRate);

      var source = _audioCtx.createMediaStreamSource(_stream);
      _scriptNode = _audioCtx.createScriptProcessor(4096, 1, 1);
      _recognizer = _newRecognizer();

      _scriptNode.onaudioprocess = function (evt) {
        if (!_running || !_recognizer) return;
        _chunkCount++;

        // 喂 PCM 数据给 Vosk Worker
        try { _recognizer.acceptWaveform(evt.inputBuffer); } catch (e) {}

        // RMS
        var d = evt.inputBuffer.getChannelData(0), rms = 0;
        for (var i = 0; i < d.length; i++) rms += d[i] * d[i];
        rms = Math.sqrt(rms / d.length);

        if (_chunkCount % 80 === 0) console.log('[WW] chunk=' + _chunkCount + ' rms=' + rms.toFixed(4) + ' partial=' + (_latestPartial || '-'));

        if (_stateCallback) _stateCallback({ rms: rms, partial: _latestPartial });
      };

      source.connect(_scriptNode);
      // scriptNode 需接入 destination 才会被拉取触发 onaudioprocess；直连会把麦克风回放到扬声器。
      // 用零增益节点保持 audio graph 活跃，同时输出静音，避免回声/啸叫。
      _muteGain = _audioCtx.createGain();
      _muteGain.gain.value = 0;
      _scriptNode.connect(_muteGain);
      _muteGain.connect(_audioCtx.destination);
      _running = true;
      console.log('[WW] listening: ' + _keywords.join(' / '));
      return true;
    } catch (e) { console.error('[WW] start fail:', e); throw e; }
  }

  function stop() {
    _running = false;
    if (_scriptNode) { _scriptNode.disconnect(); _scriptNode.onaudioprocess = null; _scriptNode = null; }
    if (_muteGain) { try { _muteGain.disconnect(); } catch (e) {} _muteGain = null; }
    _destroyRec();
    if (_audioCtx) { _audioCtx.close().catch(function () {}); _audioCtx = null; }
    if (_stream) { _stream.getTracks().forEach(function (t) { t.stop(); }); _stream = null; }
  }

  function getStream() { return _stream; }
  function isRunning() { return _running; }
  function isModelLoaded() { return _modelLoaded; }

  // ── 唤醒词匹配（keyword 驱动，适配任意关键词 + 同音字变体）──

  // 单字同音字表：唤醒词中可变字符的常见发音变体（vosk 小模型对非高频字识别率低）
  //
  // 只收**声母韵母都接近**的字，且避开在无关语句里高频出现的字 —— 每多收一个同音字，
  // 误唤醒的概率就大一分，而唤醒词最怕的就是被无关对话误触发。
  //
  // Only acoustically close characters are listed, avoiding ones that appear constantly in
  // unrelated speech: every extra homophone raises the false-wake rate, which is the main hazard
  // for a wake word.
  var _homophones = {
    // 「衍衡」
    '衍': ['演', '眼', '沿', '严', '延'],
    '衡': ['横', '恒', '哼'],
    // 「洛吉斯」
    '洛': ['罗', '落', '络', '骆', '萝', '逻'],
    '吉': ['及', '机', '即', '级', '急', '基'],
    '斯': ['思', '司', '四', '丝'],
    // 旧唤醒词的字符（仍可能被配置使用，留着无害）
    '逻': ['罗', '洛', '萝', '落', '络', '骆', '螺', '锣', '骡', '乐'],
    '邮': ['鱼', '优', '有', '游', '由', '用', '幼', '右', '油'],
  };
  // 整词误识别变体（vosk 小模型特有的整词合并/吞字，非同音字能覆盖）
  var _keywordVariants = {
    '衍衡': ['衍横', '眼衡', '演恒'],
    '洛吉斯': ['洛基斯', '罗吉斯', '洛吉思', '洛吉丝', '邏吉斯'],
    '小逻小逻': ['小逻辑', '小 逻 辑', '小罗小罗', '小洛小洛'],
    '小邮小邮': ['小游戏', '小用', '小熊效用', '小 熊 效 用'],
  };

  function _compact(s) {
    return String(s).replace(/\s+/g, '');
  }

  function _hset(ch) {
    return _homophones[ch] || [];
  }

  // 由单个 keyword 构造匹配正则：每个字 = 原字 ∪ 同音字，字间允许任意空格。
  // 例：keyword=衍衡 → /[衍演眼沿严延]\s*[衡横恒哼]/
  function _keywordRegex(key) {
    key = _compact(key);
    if (!key) return null;
    var parts = [];
    for (var i = 0; i < key.length; i++) {
      var ch = key.charAt(i);
      var set = [ch].concat(_hset(ch));
      if (set.length > 1) {
        parts.push('[' + set.join('') + ']');
      } else {
        parts.push(ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
      }
    }
    return new RegExp(parts.join('\\s*'));
  }

  // 单个唤醒词的匹配判定。A single-keyword match test.
  function _matchOne(text, compact, keyword) {
    var key = _compact(keyword);
    if (!key) return false;

    // 1) 精确匹配（含任意空格分隔）
    if (compact.indexOf(key) !== -1) return true;

    // 2) 整词误识别变体
    var variants = _keywordVariants[key] || [];
    for (var i = 0; i < variants.length; i++) {
      if (text.indexOf(variants[i]) !== -1) return true;
      if (compact.indexOf(_compact(variants[i])) !== -1) return true;
    }

    // 3) 同音字正则（原字 ∪ 同音字，字间任意空格）
    var re = _keywordRegex(key);
    if (re) {
      if (re.test(text)) return true;
      if (re.test(compact)) return true;
    }
    return false;
  }

  // 命中任意一个唤醒词即算唤醒。A hit on any configured keyword wakes the engine.
  function match(text) {
    if (!text || !_keywords.length) return false;
    var compact = _compact(text);
    for (var i = 0; i < _keywords.length; i++) {
      if (_matchOne(text, compact, _keywords[i])) return true;
    }
    return false;
  }

  return { init: init, start: start, stop: stop, getStream: getStream, isRunning: isRunning, isModelLoaded: isModelLoaded, match: match };
})();
