param(
    [string]$BasePath = "C:/models",
    [switch]$SkipLLM,
    [switch]$SkipEmbedding,
    [switch]$SkipWhisper
)

$ErrorActionPreference = "Stop"

$llmDir = Join-Path $BasePath "llm"
$embeddingDir = Join-Path $BasePath "embeddings"
$whisperDir = Join-Path $BasePath "whisper"

New-Item -ItemType Directory -Path $llmDir, $embeddingDir, $whisperDir -Force | Out-Null

function Ensure-PythonModule {
    param(
        [string]$ModuleName,
        [string]$InstallHint
    )

    try {
        python -c "import $ModuleName" | Out-Null
        return
    }
    catch {
        Write-Host "Installing $ModuleName..."
        python -m pip install $InstallHint
    }
}

if (-not $SkipLLM) {
    Write-Host "Downloading local LLM model..."
    Ensure-PythonModule -ModuleName "transformers" -InstallHint "transformers sentencepiece"
    python -c "from transformers import AutoTokenizer, AutoModelForCausalLM; AutoTokenizer.from_pretrained('Qwen/Qwen2.5-3B-Instruct'); AutoModelForCausalLM.from_pretrained('Qwen/Qwen2.5-3B-Instruct'); print('LLM_READY')"
    Write-Host "LLM model cached in the standard Hugging Face cache."
    Write-Host "Recommended path: $llmDir/Qwen2.5-3B-Instruct"
}

if (-not $SkipEmbedding) {
    Write-Host "Downloading embedding model..."
    Ensure-PythonModule -ModuleName "sentence_transformers" -InstallHint "sentence-transformers"
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); print('EMBEDDING_READY')"
    Write-Host "Embedding model cached in the standard Hugging Face cache."
    Write-Host "Recommended path: $embeddingDir/all-MiniLM-L6-v2"
}

if (-not $SkipWhisper) {
    Write-Host "Downloading Whisper model..."
    Ensure-PythonModule -ModuleName "faster_whisper" -InstallHint "faster-whisper"
    python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('WHISPER_READY')"
    Write-Host "Whisper model cached in the standard Hugging Face cache."
    Write-Host "Recommended path: $whisperDir/whisper-small"
}

Write-Host ""
Write-Host "Suggested .env entries:"
Write-Host "LLM_MODEL_PATH=C:/models/llm/Qwen2.5-3B-Instruct"
Write-Host "EMBEDDING_MODEL_PATH=C:/models/embeddings/all-MiniLM-L6-v2"
Write-Host "WHISPER_MODEL_PATH=C:/models/whisper/whisper-small"
Write-Host ""
Write-Host "Done."
