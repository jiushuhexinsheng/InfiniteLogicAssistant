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

  var _keyword = '小逻小逻';
  var _sensitivity = 0.3;       // 降低阈值以匹配更多发音变体
  var _modelPath = '/models/vosk-model-small-cn-0.22.tar.gz';
  var _modelLoaded = false;
  var _muteGain = null;         // 静音路由节点：保持 audio graph 活跃但不回放麦克风

  async function init(config) {
    config = config || {};
    _modelPath = config.modelPath || _modelPath;
    _keyword = config.keyword || _keyword;
    _sensitivity = (config.sensitivity != null) ? config.sensitivity : 0.3;
    console.log('[WW] init keyword=' + _keyword);

    if (typeof vosk === 'undefined') { console.warn('[WW] vosk missing'); return false; }
    if (_modelLoaded) return true;

    try {
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
        if (_wakeCallback) _wakeCallback();
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
        if (_wakeCallback) _wakeCallback();
      }
    });

    return r;
  }

  function _destroyRec() {
    if (_recognizer) { try { _recognizer.remove(); } catch (e) {} _recognizer = null; }
  }

  async function start(onWake, onState) {
    if (!_modelLoaded) { console.error('[WW] no model'); return false; }
    if (_running) return true;
    _wakeCallback = onWake || null;
    _stateCallback = onState || null;
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
      console.log('[WW] listening: ' + _keyword);
      return true;
    } catch (e) { console.error('[WW] start fail:', e); return false; }
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
  var _homophones = {
    '逻': ['罗', '洛', '萝', '落', '络', '骆', '螺', '锣', '骡', '乐'],
    '邮': ['鱼', '优', '有', '游', '由', '用', '幼', '右', '油'],
  };
  // 整词误识别变体（vosk 小模型特有的整词合并/吞字，非同音字能覆盖）
  var _keywordVariants = {
    '小逻小逻': ['小逻辑', '小 逻 辑', '小罗小罗', '小洛小洛'],
    '小邮小邮': ['小游戏', '小用', '小熊效用', '小 熊 效 用'],
  };

  function _compact(s) {
    return String(s).replace(/\s+/g, '');
  }

  function _hset(ch) {
    return _homophones[ch] || [];
  }

  // 由 keyword 构造匹配正则：每个字 = 原字 ∪ 同音字，字间允许任意空格。
  // 例：keyword=小逻小逻 → /小[逻罗洛落络骆螺锣骡乐]\s*小[逻罗洛落络骆螺锣骡乐]/
  function _keywordRegex() {
    var key = _compact(_keyword);
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

  function match(text) {
    if (!text || !_keyword) return false;
    var compact = _compact(text);
    var key = _compact(_keyword);

    // 1) 精确匹配（含任意空格分隔）
    if (compact.indexOf(key) !== -1) return true;

    // 2) 整词误识别变体
    var variants = _keywordVariants[key] || [];
    for (var i = 0; i < variants.length; i++) {
      if (text.indexOf(variants[i]) !== -1) return true;
      if (compact.indexOf(_compact(variants[i])) !== -1) return true;
    }

    // 3) 同音字正则（原字 ∪ 同音字，字间任意空格）
    var re = _keywordRegex();
    if (re) {
      if (re.test(text)) return true;
      if (re.test(compact)) return true;
    }
    return false;
  }

  return { init: init, start: start, stop: stop, getStream: getStream, isRunning: isRunning, isModelLoaded: isModelLoaded, match: match };
})();
