# g_inspector/hook_manager.py
"""
Перехват скрытых состояний (hidden states) модели с помощью forward hooks.
Поддерживает архитектуры LLaMA, Mistral, Qwen и другие на основе transformers.
"""

import torch
from typing import Dict, List, Optional, Any
from transformers import PreTrainedModel

def _find_layers(module):
    """Рекурсивно ищет атрибут 'layers' или 'h' в модуле."""
    if hasattr(module, 'layers') and isinstance(module.layers, list):
        return module.layers
    if hasattr(module, 'h') and isinstance(module.h, list):
        return module.h
    for child in module.children():
        result = _find_layers(child)
        if result is not None:
            return result
    return None

class HiddenStateCollector:
    """
    Сборщик активаций с указанных слоёв модели.
    Хранит активации последнего токена для каждого слоя.
    """
    def __init__(self, model: PreTrainedModel, layer_indices: Optional[List[int]] = None):
        self.model = model
        self.layers = _find_layers(model)
        if self.layers is None:
            raise RuntimeError("Не удалось найти слои модели. Проверьте структуру модели.")
        self.layer_indices = layer_indices or [-1, -2, -3]
        self.hooks = []
        self.buffer: Dict[int, torch.Tensor] = {}
        self._attach_hooks()

    def _attach_hooks(self):
        """Устанавливает forward-хуки на выбранные слои."""
        for idx in self.layer_indices:
            # Преобразуем отрицательный индекс в положительный
            actual_idx = idx if idx >= 0 else len(self.layers) + idx
            if actual_idx < 0 or actual_idx >= len(self.layers):
                raise IndexError(f"Индекс слоя {idx} вне диапазона (0..{len(self.layers)-1})")
            layer = self.layers[actual_idx]
            hook = layer.register_forward_hook(self._make_hook(actual_idx))
            self.hooks.append(hook)

    def _make_hook(self, layer_idx):
        def hook(module, input, output):
            # output может быть tuple или tensor
            out = output[0] if isinstance(output, tuple) else output
            # Берём последний токен последовательности (индекс -1)
            # Предполагаем форму [batch, seq_len, hidden_dim]
            last_token = out[:, -1, :]  # (batch, hidden_dim)
            # Сохраняем на CPU для экономии VRAM
            self.buffer[layer_idx] = last_token.detach().cpu()
        return hook

    def get_and_clear(self) -> Dict[int, torch.Tensor]:
        """Возвращает собранные активации и очищает буфер."""
        data = self.buffer.copy()
        self.buffer.clear()
        return data

    def remove_hooks(self):
        """Удаляет все установленные хуки."""
        for hook in self.hooks:
            hook.remove()
        self.hooks = []
