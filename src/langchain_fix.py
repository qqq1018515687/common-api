"""
修复 langchain_core.exceptions 中缺失的 ContextOverflowError
"""
try:
    from langchain_core.exceptions import ContextOverflowError
except ImportError:
    # 如果 ContextOverflowError 不存在，创建一个空类
    from langchain_core.exceptions import LangChainException
    
    class ContextOverflowError(LangChainException):
        """ContextOverflowError - 用于兼容性"""
        pass
