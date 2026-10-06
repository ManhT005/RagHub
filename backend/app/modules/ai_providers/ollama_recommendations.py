"""Small curated catalog; sizes from https://ollama.com/library/{gemma3,qwen3}.

Download sizes are approximate, not runtime RAM/VRAM requirements. Reviewed 2026-10-05.
"""

RECOMMENDATIONS = [
    {
        "model": model,
        "display_name": name,
        "tier": tier,
        "size_bytes": size,
        "description": description,
        "highlighted": highlighted,
    }
    for model, name, tier, size, description, highlighted in (
        ("gemma3:1b", "Gemma 3 1B", "Tiny", 815_000_000, "Nhanh, phù hợp máy ít tài nguyên", True),
        ("qwen3:1.7b", "Qwen3 1.7B", "Small", 1_400_000_000, "Đa ngôn ngữ, nhẹ", True),
        ("qwen3:4b", "Qwen3 4B", "Balanced", 2_500_000_000, "Cân bằng cho self-host", True),
        ("gemma3:4b", "Gemma 3 4B", "Balanced+", 3_300_000_000, "Chat tổng quát", True),
        ("qwen3:8b", "Qwen3 8B", "Medium", 5_200_000_000, "Cần nhiều bộ nhớ hơn", False),
        ("gemma3:12b", "Gemma 3 12B", "Large", 8_100_000_000, "Dành cho máy mạnh", False),
        ("gemma3:27b", "Gemma 3 27B", "XL", 17_000_000_000, "Cần host có nhiều RAM/VRAM", False),
    )
]
