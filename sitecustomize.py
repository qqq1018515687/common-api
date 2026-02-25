"""
全局修复 langchain_core 中缺失的类
"""
import langchain_core.exceptions
import langchain_core.language_models

# 修复 ContextOverflowError
if not hasattr(langchain_core.exceptions, 'ContextOverflowError'):
    class ContextOverflowError(langchain_core.exceptions.LangChainException):
        """ContextOverflowError - 用于兼容性"""
        pass
    langchain_core.exceptions.ContextOverflowError = ContextOverflowError

# 修复 ModelProfileRegistry
if not hasattr(langchain_core.language_models, 'ModelProfileRegistry'):
    class ModelProfileRegistry:
        """ModelProfileRegistry - 用于兼容性"""
        @staticmethod
        def get_default_model_profile(model_name):
            return None
    langchain_core.language_models.ModelProfileRegistry = ModelProfileRegistry
