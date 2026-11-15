"""插件层：出题生成器与判题器。

当前只固化接口和默认实现，不加载第三方代码、不做插件市场。
后续新增插件时，在 registry 中注册并实现对应 Protocol 即可。
"""
from app.plugins.base import (  # noqa: F401
    GradingContext,
    GradingCriterion,
    GradingPlan,
    GradeResult,
    GradeCriterionResult,
    GenerationContext,
    PublicQuestion,
    Question,
    TestCase,
)
from app.plugins.registry import (  # noqa: F401
    DEFAULT_GENERATOR_ID,
    DEFAULT_GRADER_ID,
    get_grader,
    list_plugins,
)
