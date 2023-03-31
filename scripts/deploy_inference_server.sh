# This script is used to deploy the inference of CodeGeeX.

GPU=$1

SCRIPT_PATH=$(realpath "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
MAIN_DIR=$(dirname "$SCRIPT_DIR")
TOKENIZER_PATH="$MAIN_DIR/codegeex/tokenizer/"

echo "$MAIN_DIR"

# import model configuration
source "$MAIN_DIR/configs/codegeex_13b.sh"

# export CUDA settings
if [ -z "$GPU" ]; then
  GPU=0
fi

export CUDA_VISIBLE_DEVICES=$GPU

# remove --greedy if using sampling
CMD="python $MAIN_DIR/deployment/server_api_flask.py \
        --tokenizer-path $TOKENIZER_PATH \
        --micro-batch-size 1 \
        --out-seq-length 64 \
        --temperature 0.8 \
        --top-p 0.95 \
        --top-k 0 \
        --greedy \
        $MODEL_ARGS"

echo "$MODEL_ARGS"

echo "$CMD"
eval "$CMD"
