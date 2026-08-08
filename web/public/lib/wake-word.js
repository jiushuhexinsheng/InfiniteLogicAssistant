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

  var _keyword = '小邮小邮';
  var _sensitivity = 0.3;       // 降低阈值以匹配更多发音变体
  var _modelPath = '/models/vosk-model-small-cn-0.22.tar.gz';
  var _modelLoaded = false;

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
      _scriptNode.connect(_audioCtx.destination);
      _running = true;
      console.log('[WW] listening: ' + _keyword);
      return true;
    } catch (e) { console.error('[WW] start fail:', e); return false; }
  }

  function stop() {
    _running = false;
    if (_scriptNode) { _scriptNode.disconnect(); _scriptNode.onaudioprocess = null; _scriptNode = null; }
    _destroyRec();
    if (_audioCtx) { _audioCtx.close().catch(function () {}); _audioCtx = null; }
    if (_stream) { _stream.getTracks().forEach(function (t) { t.stop(); }); _stream = null; }
  }

  function getStream() { return _stream; }
  function isRunning() { return _running; }
  function isModelLoaded() { return _modelLoaded; }

  function match(text) {
    if (!text || !_keyword) return false;
    if (text.indexOf(_keyword) !== -1) return true;
    // 去除所有空格做归一化匹配
    var compact = text.replace(/\s+/g, '');
    if (compact.indexOf('小邮小邮') !== -1) return true;

    // 发音变体覆盖 (Vosk 小模型对 '邮' 识别率低)
    var variants = [
      '小鱼小鱼','小优小优','小有小有','小游小游','小由小由',
      '小鱼 小鱼','小优 小优','小有 小有','小游 小游','小由 小由',
      '小游戏',        // vosk 常见误识别: "小游戏" ≈ "小邮"
      '小用',          // vosk 短识别
      '小熊效用','小熊 效用','小 熊 效 用',
    ];
    for (var i = 0; i < variants.length; i++) {
      if (text.indexOf(variants[i]) !== -1) return true;
      if (compact.indexOf(variants[i].replace(/\s+/g, '')) !== -1) return true;
    }

    // 双字匹配: 小X(空格?)小Y 其中 X,Y ∈ 同音字集
    var cs = ['邮','鱼','优','有','游','由','用','戏','熊','效'];
    // 紧凑形式: 小X小Y
    for (var a = 0; a < cs.length; a++) {
      for (var b = 0; b < cs.length; b++) {
        if (compact.indexOf('小' + cs[a] + '小' + cs[b]) !== -1) return true;
      }
    }
    // 宽松形式: "小 X 小 Y" 任意空格分隔 (覆盖 "小 有 小 有")
    var re = /小\s*(\S)\s*小\s*(\S)/g;
    var m;
    while ((m = re.exec(text)) !== null) {
      if (cs.indexOf(m[1]) !== -1 && cs.indexOf(m[2]) !== -1) return true;
    }

    return false;
  }

  return { init: init, start: start, stop: stop, getStream: getStream, isRunning: isRunning, isModelLoaded: isModelLoaded };
})();
