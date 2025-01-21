& 'D:\Program Files\Miniconda3\shell\condabin\conda-hook.ps1'
conda activate FunASR

# 设置基本变量
$download_model_dir = "D:\Application\FunASR\funasr-runtime-resources\models"
$model_dir = "damo/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx"
$online_model_dir = "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online-onnx"
$vad_dir = "damo/speech_fsmn_vad_zh-cn-16k-common-onnx"
$punc_dir = "damo/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727-onnx"
$itn_dir = "thuduj12/fst_itn_zh"
$lm_dir = "damo/speech_ngram_lm_zh-cn-ai-wesp-fst"
$port = 10096
$certfile = 0
$keyfile = 0
$hotword = "D:\Application\FunASR\FunASR\runtime\websocket\hotwords.txt"

# 获取CPU核心数
$decoder_thread_num = (Get-WmiObject -Class Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
if (-not $decoder_thread_num) {
    Write-Host "Get cpuinfo failed. Set decoder_thread_num = 32"
    $decoder_thread_num = 32
}

$multiple_io = 16
$io_thread_num = [Math]::Ceiling($decoder_thread_num / $multiple_io)
$model_thread_num = 1

$cmd_path = "D:\Application\FunASR\FunASR\runtime\websocket\build\bin\Debug"
$cmd = "funasr-wss-server-2pass.exe"

# 检查证书文件
if (-not (Test-Path $certfile) -or $certfile -eq "0") {
    $certfile = ""
    $keyfile = ""
}

# 切换到命令目录
Set-Location $cmd_path

# 构建参数数组
$arguments = @(
    "--download-model-dir", $download_model_dir,
    "--model-dir", $model_dir,
    "--online-model-dir", $online_model_dir,
    "--vad-dir", $vad_dir,
    "--punc-dir", $punc_dir,
    "--itn-dir", $itn_dir,
    "--lm-dir", $lm_dir,
    "--decoder-thread-num", $decoder_thread_num,
    "--model-thread-num", $model_thread_num,
    "--io-thread-num", $io_thread_num,
    "--port", $port,
    "--certfile", $certfile,
    "--keyfile", $keyfile,
    "--hotword", $hotword
)

# 启动服务器
try {
    & "$cmd_path\$cmd" $arguments
}
catch {
    Write-Error "Failed to start server: $_"
    exit 1
}
