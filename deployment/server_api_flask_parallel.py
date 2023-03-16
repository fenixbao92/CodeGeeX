from flask import Flask, jsonify
from flask import request
import time


import copy
import time
import torch
import numpy as np

from codegeex.megatron import get_tokenizer, get_args, print_rank_0
from codegeex.megatron.initialize import initialize_megatron
from codegeex.megatron.model import CodeGeeXModel
from codegeex.megatron.code_generation_utils import get_token_stream
from codegeex.quantization import quantize
from codegeex.megatron.training import get_model
from codegeex.megatron.checkpointing import load_checkpoint

import codegeex

torch.set_printoptions(precision=8)


def set_random_seed(seed):
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def model_provider(pre_process=True, post_process=True):
    """Build the model."""
    
    print_rank_0("Server Building CodeGeeX model ...")
    model = CodeGeeXModel(num_tokentypes=0,
                          parallel_output=False)

    return model


def add_code_generation_args(parser):
    """Code generation arguments."""
    group = parser.add_argument_group(title="code generation")

    group.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature.",
    )
    group.add_argument(
        "--greedy",
        action="store_true",
        default=False,
        help="Use greedy sampling.",
    )
    group.add_argument(
        "--top-p",
        type=float,
        default=0.0,
        help="Top p sampling.",
    )
    group.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Top k sampling.",
    )
    group.add_argument(
        "--out-seq-length",
        type=int,
        default=2048,
        help="Size of the output generated text.",
    )
    group.add_argument(
        "--recompute",
        action="store_true",
        help="During generation recompute all attention "
             "instead of using previously computed keys/values.",
    )
    group.add_argument(
        "--ws-encoding-start-id",
        type=int,
        default=10,
        help="Start id for whitespace encoding",
    )
    group.add_argument(
        "--ws-encoding-length",
        type=int,
        default=10,
        help="Length of whitespace encoding",
    )
    group.add_argument(
        "--n-generation",
        type=int,
        default=10,
    )
    group.add_argument(
        "--eos-id",
        type=int,
        default=50256,
    )
    group.add_argument(
        "--prompt-file",
        type=str,
        default="./test_prompt.txt",
    )
    group.add_argument(
        "--perf-file",
        type=str,
        default="./perf_out.txt",
    )
    group.add_argument(
        "--perf-trace",
        type=str,
        default="./perf_out.txt",
    )
    group.add_argument(
        "--use-torch-profile",
        action="store_true",
    )
    group.add_argument(
        "--ln-fp32",
        action="store_true",
    )
    group.add_argument(
        '--bad-ids',
        nargs="*",
        type=int,
        default=None,
        help='Identify the type of programming language to generate',
    )
    group.add_argument(
        "--quantize",
        action="store_true",
    )

    return parser

app = Flask(__name__)

def main():
    initialize_megatron(
        extra_args_provider=add_code_generation_args,
        args_defaults={
            'no_load_rng': True,
            'no_load_optim': True,
        }
    )

    args = get_args()
    set_random_seed(args.seed)

    print_rank_0("Server Loading tokenizer ...")
    tokenizer = get_tokenizer()

    print_rank_0("Server Loading state dict ...")

    model = get_model(model_provider)
    if args.load is not None:
        _ = load_checkpoint(model, None, None)
    
    assert len(model) == 1, "Above condition should have caught this"
    
    model = model[0]
    model.eval()
    if args.fp16 and args.ln_fp16:
        model.half()
    # if args.quantize:
    #     model = quantize(model, weight_bit_width=8, backend="megatron")

    # with open(args.prompt_file, "r") as f:
    #     prompt = f.readlines()
    #     prompt = "".join(prompt)
    
    print("=============app===============")
    @app.route('/predict', methods=['POST'])
    def predict():
        json_ = request.json
        prompt = json_["prompt"];
        length = json_["len"]
        prompt = "// language: Java" + "\n" + prompt
        micro_batch_size = args.micro_batch_size
        t0 = time.perf_counter()
        tokens = tokenizer.tokenize(prompt)
        print_rank_0(tokens)
        print_rank_0("Current prompt:")
        print_rank_0(prompt)
        n_token_prompt = len(tokens)
        print_rank_0(f"N_token_prompt:{n_token_prompt}")
        token_stream = get_token_stream(
            model,
            [copy.deepcopy(tokens) for _ in range(micro_batch_size)],
            micro_batch_size=micro_batch_size,
            topk=args.top_k,
            topp=args.top_p,
            temperature=args.temperature,
        )
        out_seq_length = length + n_token_prompt
        is_finished = [False for _ in range(micro_batch_size)]
        for i, generated in enumerate(token_stream):
            generated_tokens = generated[0]
            j = 0;
            if generated_tokens[j].cpu().numpy()[-1] == tokenizer.eod or len(
                    generated_tokens[j]) >= out_seq_length:
                is_finished[j] = True
                generated_tokens_ = generated_tokens[j].cpu().numpy().tolist()
                generated_code = tokenizer.detokenize(generated_tokens_[n_token_prompt:])
                print_rank_0("================================= Generated code:")
                print_rank_0(generated_code)
                print_rank_0("================================= Generated code end")
                
            if all(is_finished):
                break 
        t1 = time.perf_counter()
        print("Total generation time:", t1 - t0)
        return {"result":generated_code,"time":t1 - t0,"len":length}
    print("Server to Deployed")
    try:
        app.run(debug=False)
    except e:
        pass 
    print("Server Deployed ...")

if __name__ == "__main__":
    with torch.no_grad():
        main()