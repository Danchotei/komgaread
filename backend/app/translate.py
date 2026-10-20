from opencc import OpenCC

# 启动时加载词典并复用，不在每次搜索时重复初始化。
_to_simple = OpenCC('t2s')
_to_traditional = OpenCC('s2t')
_to_taiwan = OpenCC('s2tw')
_to_hongkong = OpenCC('s2hk')


def keyword_variants(text: str) -> list[str]:
    original = text.strip()
    simple = _to_simple.convert(original)
    return list(dict.fromkeys([
        original, simple, _to_traditional.convert(simple),
        _to_taiwan.convert(simple), _to_hongkong.convert(simple),
    ]))
