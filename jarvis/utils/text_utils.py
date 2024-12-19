import json
from typing import Optional, Any

def extract_json_from_text(text: str) -> Optional[Any]:
    """
    从文本中提取 JSON 内容。
    
    Args:
        text: 可能包含 JSON 的文本字符串
        
    Returns:
        解析后的 JSON 对象，如果没有找到有效的 JSON 则返回 None
        
    示例:
        >>> text = "这是一些文本 {\"key\": \"value\"} 后面的文本"
        >>> result = extract_json_from_text(text)
        >>> print(result)
        {'key': 'value'}
    """
    # 找到第一个左花括号和最后一个右花括号的位置
    start = text.find('{')
    if start == -1:
        return None
        
    end = text.rfind('}')
    if end == -1:
        return None
        
    # 提取可能的 JSON 字符串
    json_str = text[start:end + 1]
    
    # 尝试解析 JSON

    return json.loads(json_str)


if __name__ == "__main__":
    text = "这是一些文本 {\"key\": \"value\"} 后面的文本"
    result = extract_json_from_text(text)
    print(result)