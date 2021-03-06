"""Secondary Structure dataset."""

import numpy as np
from megatron import print_rank_0
from .data import ProteinPredictionAbstractDataset
from .data import build_tokens_paddings_from_text

class SecondaryStructureDataset(ProteinPredictionAbstractDataset):
    def __init__(self,
                name: str,
                datapaths,
                tokenizer,
                max_seq_length: int):
        super().__init__('secondary_structure', name, datapaths, tokenizer, max_seq_length)


    def build_samples(self, ids, paddings, label, unique_id, seq_len):
        """Convert to numpy and return a sample consumed by the batch producer."""

        ids_np = np.array(ids, dtype=np.int64)
        paddings_np = np.array(paddings, dtype=np.int64)

        label = [-1] + label
        padding_length = self.max_seq_length - len(label)
        if padding_length > 0:
            label.extend([-1] * padding_length)
        label = label[:self.max_seq_length]
        label_np = np.array(label, dtype=np.int64)
        sample = ({'text': ids_np,
                'padding_mask': paddings_np,
                'label': label_np,
                'uid': int(unique_id),
                'seq_len': int(seq_len)})
        return sample
    
    def __getitem__(self, index: int):
        item = self.samples[index]
        ids, paddings, seq_len = build_tokens_paddings_from_text(
            item['primary'], self.tokenizer, self.max_seq_length)
        seq_len = min(seq_len + 1, self.max_seq_length) # +1 because of the [cls] token
        sample = self.build_samples(ids, paddings, item['ss3'].tolist(), item['uid'], seq_len)
        return sample
