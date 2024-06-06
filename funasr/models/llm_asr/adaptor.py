import torch
import torch.nn as nn
import torch.nn.functional as F
from funasr.models.transformer.utils.nets_utils import make_pad_mask

from funasr.register import tables


@tables.register("adaptor_classes", "Linear")
class Linear(nn.Module):
    def __init__(self, downsample_rate, encoder_dim, llm_dim, ffn_dim: int = 2048, **kwargs):
        super().__init__()
        self.k = downsample_rate
        self.encoder_dim = encoder_dim
        self.llm_dim = llm_dim
        self.linear1 = nn.Linear(self.encoder_dim * self.k, ffn_dim)
        self.relu = nn.ReLU()
        self.linear2 = nn.Linear(ffn_dim, self.llm_dim)

    def forward(self, x):
        batch_size, seq_len, dim = x.size()
        num_frames_to_discard = seq_len % self.k
        if num_frames_to_discard > 0:
            x = x[:, :-num_frames_to_discard, :]
        seq_len = x.size(1)

        x = x.contiguous()
        x = x.view(batch_size, seq_len // self.k, dim * self.k)
        x = self.linear1(x)
        x = self.relu(x)
        x = self.linear2(x)
        return x


@tables.register("adaptor_classes", "QFormer")
class EncoderProjectorQFormer(nn.Module):
    def __init__(self, downsample_rate, encoder_dim, llm_dim, ffn_dim: int = 2048, **kwargs):
        super().__init__()
        self.encoder_dim = encoder_dim
        self.llm_dim = llm_dim
        from transformers import Blip2QFormerConfig, Blip2QFormerModel

        configuration = Blip2QFormerConfig()
        configuration.encoder_hidden_size = self.encoder_dim
        configuration.num_hidden_layers = 2

        self.query_len = 64
        self.query = nn.Parameter(torch.zeros(1, self.query_len, configuration.hidden_size))
        self.query.data.normal_(mean=0.0, std=1.0)
        self.qformer = Blip2QFormerModel(configuration)

        self.linear = nn.Linear(configuration.hidden_size, self.llm_dim)
        self.norm = nn.LayerNorm(self.llm_dim, eps=1e-5)

    def forward(self, x, atts):
        query = self.query.expand(x.shape[0], -1, -1)

        query_output = self.qformer(
            query_embeds=query,
            encoder_hidden_states=x,
            encoder_attention_mask=atts,
            return_dict=True,
        )

        query_proj = self.norm(self.linear(query_output.last_hidden_state))

        return query_proj


@tables.register("adaptor_classes", "Transformer")
class Transformer(nn.Module):
    def __init__(
        self, downsample_rate=2, encoder_dim=1280, llm_dim=4096, ffn_dim: int = 2048, **kwargs
    ):
        super().__init__()
        self.k = downsample_rate
        self.encoder_dim = encoder_dim
        self.llm_dim = llm_dim
        self.linear1 = nn.Linear(self.encoder_dim * self.k, ffn_dim)
        self.relu = nn.ReLU()
        self.linear2 = nn.Linear(ffn_dim, self.llm_dim)
        from funasr.models.transformer.encoder import EncoderLayer
        from funasr.models.transformer.attention import MultiHeadedAttention
        from funasr.models.transformer.positionwise_feed_forward import PositionwiseFeedForward

        self.blocks = nn.ModuleList(
            [
                EncoderLayer(
                    llm_dim,
                    MultiHeadedAttention(
                        kwargs.get("attention_heads", 8),
                        llm_dim,
                        kwargs.get("attention_dropout_rate", 0.0),
                    ),
                    PositionwiseFeedForward(
                        llm_dim,
                        llm_dim // 4,
                        kwargs.get("dropout_rate", 0.0),
                    ),
                    kwargs.get("dropout_rate", 0.0),
                )
                for i in range(kwargs.get("n_layer", 2))
            ]
        )

    def forward(self, x, ilens=None):

        batch_size, seq_len, dim = x.size()
        # num_frames_to_discard = seq_len % self.k
        chunk_num = (seq_len - 1) // self.k + 1
        pad_num = chunk_num * self.k - seq_len
        x = F.pad(x, (0, 0, 0, pad_num, 0, 0), value=0.0)
        # if num_frames_to_discard > 0:
        #     x = x[:, :-num_frames_to_discard, :]
        seq_len = x.size(1)

        x = x.contiguous()
        x = x.view(batch_size, chunk_num, dim * self.k)
        x = self.linear1(x)
        x = self.relu(x)
        x = self.linear2(x)

        olens = None
        olens = (ilens - 1) // self.k + 1
        masks = (~make_pad_mask(olens)[:, None, :]).to(x.device)
        for layer, block in enumerate(self.blocks):
            x, masks = block(x, masks)
        return x, olens
