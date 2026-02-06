# 时间字段类型变更说明

## 概述
为了支持前端传递字符串类型的时间戳，将 tasks 表中的时间字段类型从 `NUMBER(BIGINT)` 修改为 `VARCHAR(30)`。

## 修改内容

### 1. 数据库表结构变更

#### tasks 表
| 字段名 | 原类型 | 新类型 | 说明 |
|--------|--------|--------|------|
| created_at | BIGINT | VARCHAR(30) | 任务创建时间 |
| updated_at | BIGINT | VARCHAR(30) | 任务更新时间 |
| completed_at | BIGINT | VARCHAR(30) | 完成时间（可为空） |
| disconnected_at | - | VARCHAR(30) | 断开时间（新增字段，可为空） |

### 2. 代码变更

#### 模型定义 (`src/storage/database/shared/model.py`)
```python
# 修改前
created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
completed_at: Mapped[Optional[int]] = mapped_column(BigInteger)

# 修改后
created_at: Mapped[str] = mapped_column(String(30), nullable=False, comment="任务创建时间")
updated_at: Mapped[str] = mapped_column(String(30), nullable=False, comment="任务更新时间")
completed_at: Mapped[Optional[str]] = mapped_column(String(30), comment="完成时间")
disconnected_at: Mapped[Optional[str]] = mapped_column(String(30), comment="断开时间")  # 新增
```

#### 任务管理器 (`src/storage/database/task_manager.py`)

**TaskUpdate 数据类修改：**
```python
# 修改前
class TaskUpdate(BaseModel):
    completed_at: Optional[int] = Field(default=None, description="完成时间")

# 修改后
class TaskUpdate(BaseModel):
    completed_at: Optional[str] = Field(default=None, description="完成时间")
```

**时间赋值修改：**
```python
# 修改前
current_time = int(time.time() * 1000)
task_data['created_at'] = current_time
task_data['updated_at'] = current_time

# 修改后
current_time = str(int(time.time() * 1000))
task_data['created_at'] = current_time
task_data['updated_at'] = current_time
```

### 3. 数据库迁移

迁移文件：`migrations/versions/a1b2c3d4e5f6_change_timestamp_fields_to_varchar_.py`

```python
def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('created_at',
               existing_type=sa.BigInteger(),
               type_=sa.String(30),
               existing_nullable=False,
               comment='任务创建时间')
        batch_op.alter_column('updated_at',
               existing_type=sa.BigInteger(),
               type_=sa.String(30),
               existing_nullable=False,
               comment='任务更新时间')
        batch_op.alter_column('completed_at',
               existing_type=sa.BigInteger(),
               type_=sa.String(30),
               existing_nullable=True,
               comment='完成时间')
        batch_op.add_column(sa.Column('disconnected_at', sa.String(30), nullable=True, comment='断开时间'))
```

## 迁移执行

```bash
# 执行迁移
alembic upgrade head

# 回滚迁移
alembic downgrade a1b2c3d4e5f6
```

## 兼容性说明

- ✅ 支持字符串类型的时间戳（如 "1770347399006"）
- ✅ 历史数据会自动转换为字符串格式
- ✅ deduction_result 保护机制仍然有效
- ✅ 前端可以直接传递字符串类型的时间字段

## 测试验证

| 测试项 | 结果 |
|--------|------|
| 创建任务（字符串时间戳） | ✅ 通过 |
| 更新任务（字符串 completed_at） | ✅ 通过 |
| deduction_result 保护机制 | ✅ 通过 |
| 多次更新不覆盖 deduction_result | ✅ 通过 |
| disconnected_at 字段新增 | ✅ 通过 |

## 相关文档

- [扣费结果字段说明](./DEDUCTION_RESULT_FIELD.md)
- [数据库迁移指南](./ALEMBIC_GUIDE.md)
