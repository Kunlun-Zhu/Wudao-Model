# coding=utf-8
# Copyright (c) 2019, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GPT-2 model."""

import torch
import torch.nn.functional as F

import mpu


def init_method_normal(std=0.02):
    """Init method based on normal distribution.

    This is only used for embeddings. The transformer has its
    own initializer.
    """
    def init_(tensor):
        return torch.nn.init.normal_(tensor, mean=0.0, std=std)
    return init_


def gpt2_get_params_for_weight_decay_optimization(module):

    weight_decay_params = {'params': []}
    no_weight_decay_params = {'params': [], 'weight_decay': 0.0}
    for module_ in module.modules():
        if isinstance(module_, (mpu.LayerNorm, torch.nn.LayerNorm)):
            no_weight_decay_params['params'].extend(
                [p for p in list(module_._parameters.values())
                 if p is not None])
        else:
            weight_decay_params['params'].extend(
                [p for n, p in list(module_._parameters.items())
                 if p is not None and n != 'bias'])
            no_weight_decay_params['params'].extend(
                [p for n, p in list(module_._parameters.items())
                 if p is not None and n == 'bias'])

    return weight_decay_params, no_weight_decay_params


class GPT2Model(torch.nn.Module):
    """GPT-2 Language model.

    The output of the forward method are the logits (parallel or
    serial depending on the `parallel_output` flag.
    """

    def __init__(self,
                 num_layers,
                 vocab_size,
                 hidden_size,
                 num_attention_heads,
                 embedding_dropout_prob,
                 attention_dropout_prob,
                 output_dropout_prob,
                 max_sequence_length,
                 max_memory_length,
                 checkpoint_activations,
                 checkpoint_num_layers=1,
                 parallel_output=True,
                 query_window=128,
                 key_window_times=6,
                 num_pivot=768
                 ):

        super(GPT2Model, self).__init__()

        self.parallel_output = parallel_output

        init_method = init_method_normal(std=0.02)

        # Word embeddings (parallel).
        self.word_embeddings = mpu.VocabParallelEmbedding(
            vocab_size, hidden_size, init_method=init_method)

        # Transformer
        self.transformer = mpu.GPT2ParallelTransformer(num_layers,
                                                       hidden_size,
                                                       num_attention_heads,
                                                       max_sequence_length,
                                                       max_memory_length,
                                                       embedding_dropout_prob,
                                                       attention_dropout_prob,
                                                       output_dropout_prob,
                                                       checkpoint_activations,
                                                       checkpoint_num_layers,
                                                       query_window=query_window,
                                                       key_window_times=key_window_times,
                                                       num_pivot=num_pivot
                                                       )

    def forward(self, input_ids, position_ids, attention_mask, txt_indices_bool, img_indices_bool, is_sparse, *mems):
        # Embeddings.
        words_embeddings = self.word_embeddings(input_ids)
        embeddings = words_embeddings

        # Transformer.
        transformer_output = self.transformer(embeddings, position_ids, attention_mask, txt_indices_bool, img_indices_bool, is_sparse, *mems)
        logits, *hidden_layers = transformer_output
        # Parallel logits.
        logits_parallel = mpu.copy_to_model_parallel_region(
            logits)
        logits_parallel = F.linear(logits_parallel,
                                   self.word_embeddings.weight)

        if self.parallel_output:
            return (logits_parallel, *hidden_layers)

        return (mpu.gather_from_model_parallel_region(logits_parallel), *hidden_layers)
