# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import tinker

service_client = tinker.ServiceClient()
print("Available models:")
for item in service_client.get_server_capabilities().supported_models:
    print("- " + item.model_name)

base_model = "Qwen/Qwen3-30B-A3B-Base"
training_client = service_client.create_lora_training_client(base_model=base_model)

# Create some training examples
examples = [
    {"input": "banana split", "output": "anana-bay plit-say"},
    {"input": "quantum physics", "output": "uantum-qay ysics-phay"},
    {"input": "donut shop", "output": "onut-day op-shay"},
    {"input": "pickle jar", "output": "ickle-pay ar-jay"},
    {"input": "space exploration", "output": "ace-spay exploration-way"},
    {"input": "rubber duck", "output": "ubber-ray uck-day"},
    {"input": "coding wizard", "output": "oding-cay izard-way"},
]

# Convert examples into the format expected by the training client
from tinker import types

# Get the tokenizer from the training client
tokenizer = training_client.get_tokenizer()


def process_example(example: dict, tokenizer) -> types.Datum:
    # Format the input with Input/Output template
    # For most real use cases, you'll want to use a renderer / chat template,
    # (see later docs) but here, we'll keep it simple.
    prompt = f"English: {example['input']}\nPig Latin:"

    prompt_tokens = tokenizer.encode(prompt, add_special_tokens=True)
    prompt_weights = [0] * len(prompt_tokens)
    # Add a space before the output string, and finish with double newline
    completion_tokens = tokenizer.encode(f" {example['output']}\n\n", add_special_tokens=False)
    completion_weights = [1] * len(completion_tokens)

    tokens = prompt_tokens + completion_tokens
    weights = prompt_weights + completion_weights

    input_tokens = tokens[:-1]
    target_tokens = tokens[1:]  # We're predicting the next token, so targets need to be shifted.
    weights = weights[1:]

    # A datum is a single training example for the loss function.
    # It has model_input, which is the input sequence that'll be passed into the LLM,
    # loss_fn_inputs, which is a dictionary of extra inputs used by the loss function.
    return types.Datum(
        model_input=types.ModelInput.from_ints(tokens=input_tokens),
        loss_fn_inputs=dict(weights=weights, target_tokens=target_tokens),
    )


processed_examples = [process_example(ex, tokenizer) for ex in examples]

# Visualize the first example for debugging purposes
datum0 = processed_examples[0]
print(f"{'Input':<20} {'Target':<20} {'Weight':<10}")
print("-" * 50)
for i, (inp, tgt, wgt) in enumerate(
    zip(
        datum0.model_input.to_ints(),
        datum0.loss_fn_inputs["target_tokens"].tolist(),
        datum0.loss_fn_inputs["weights"].tolist(),
    )
):
    print(f"{repr(tokenizer.decode([inp])):<20} {repr(tokenizer.decode([tgt])):<20} {wgt:<10}")

import numpy as np

for _ in range(6):
    fwdbwd_future = training_client.forward_backward(processed_examples, "cross_entropy")
    optim_future = training_client.optim_step(types.AdamParams(learning_rate=1e-4))

    # Wait for the results
    fwdbwd_result = fwdbwd_future.result()
    optim_result = optim_future.result()

    # fwdbwd_result contains the logprobs of all the tokens we put in. Now we can compute the weighted
    # average log loss per token.
    logprobs = np.concatenate([output["logprobs"].tolist() for output in fwdbwd_result.loss_fn_outputs])
    weights = np.concatenate([example.loss_fn_inputs["weights"].tolist() for example in processed_examples])
    print(f"Loss per token: {-np.dot(logprobs, weights) / weights.sum():.4f}")

# First, create a sampling client. We need to transfer weights
sampling_client = training_client.save_weights_and_get_sampling_client(name="pig-latin-model")

# Now, we can sample from the model.
prompt = types.ModelInput.from_ints(tokenizer.encode("English: coffee break\nPig Latin:"))
params = types.SamplingParams(max_tokens=20, temperature=0.0, stop=["\n"])  # Greedy sampling
future = sampling_client.sample(prompt=prompt, sampling_params=params, num_samples=8)
result = future.result()
print("Responses:")
for i, seq in enumerate(result.sequences):
    print(f"{i}: {repr(tokenizer.decode(seq.tokens))}")
