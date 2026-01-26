# Alembic 数据库迁移指南

## 📖 什么是 Alembic？

Alembic 是 SQLAlchemy 的数据库迁移工具，用于管理数据库表结构的变更历史。它类似于 Git，但是是用于数据库版本管理的。

## 🎯 为什么需要 Alembic？

- ✅ **版本记录**：记录每次表结构的修改
- ✅ **团队协作**：避免团队成员数据库结构不一致
- ✅ **一键同步**：新同事加入，一条命令同步数据库
- ✅ **可回滚**：改错了可以回滚到上一个版本
- ✅ **环境一致**：开发、测试、生产环境表结构完全一致

## 🚀 快速开始

### 1. 查看当前版本

```bash
# 查看当前数据库版本
alembic current

# 查看所有迁移历史
alembic history
```

### 2. 修改表结构

当你需要修改数据库表结构时：

#### 步骤 1：修改模型定义

```python
# src/storage/database/shared/model.py

class Users(Base):
    __tablename__ = 'users'

    # ... 现有字段 ...

    # 新增字段示例
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment='用户昵称')
```

#### 步骤 2：生成迁移脚本

```bash
# 自动生成迁移脚本
alembic revision --autogenerate -m "添加用户昵称字段"
```

这个命令会在 `migrations/versions/` 目录下生成一个新的迁移脚本，例如：
```
migrations/versions/20240126_120000_添加用户昵称字段.py
```

#### 步骤 3：检查迁移脚本

查看生成的迁移脚本，确认 SQL 语句是否正确：

```python
# migrations/versions/xxxx_添加用户昵称字段.py

def upgrade() -> None:
    """添加用户昵称字段"""
    op.add_column('users', sa.Column('nickname', sa.String(100), nullable=True))

def downgrade() -> None:
    """移除用户昵称字段"""
    op.drop_column('users', 'nickname')
```

#### 步骤 4：应用迁移

```bash
# 应用所有未执行的迁移
alembic upgrade head

# 应用到指定版本
alembic upgrade 20240126_120000
```

#### 步骤 5：提交到 Git

```bash
git add migrations/versions/xxxx_添加用户昵称字段.py
git commit -m "feat: 添加用户昵称字段"
git push
```

### 3. 回滚迁移

如果迁移有问题，可以回滚：

```bash
# 回滚到上一个版本
alembic downgrade -1

# 回滚到指定版本
alembic downgrade 000000000000

# 回滚到初始状态
alembic downgrade base
```

### 4. 查看迁移状态

```bash
# 查看当前版本
alembic current

# 查看所有迁移历史
alembic history

# 查看待执行的迁移
alembic check
```

## 📝 常见操作场景

### 场景 1：添加新字段

```python
# 1. 修改模型
class Users(Base):
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

# 2. 生成迁移
alembic revision --autogenerate -m "添加昵称字段"

# 3. 应用迁移
alembic upgrade head
```

### 场景 2：修改字段类型

```python
# 1. 修改模型
class Users(Base):
    phone: Mapped[Optional[str]] = mapped_column(String(20))  # 从 11 改为 20

# 2. 生成迁移
alembic revision --autogenerate -m "修改手机号字段长度"

# 3. 应用迁移
alembic upgrade head
```

### 场景 3：添加唯一约束

```python
# 1. 修改模型
class Users(Base):
    __table_args__ = (
        UniqueConstraint('email', name='users_email_key'),
        # ... 其他约束 ...
    )

# 2. 生成迁移
alembic revision --autogenerate -m "添加邮箱唯一约束"

# 3. 应用迁移
alembic upgrade head
```

### 场景 4：创建新表

```python
# 1. 新建模型
class UserProfiles(Base):
    __tablename__ = 'user_profiles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(10), unique=True)
    bio: Mapped[Optional[str]] = mapped_column(Text)

# 2. 记得在 env.py 中导入
# migrations/env.py
from storage.database.shared.model import UserProfiles

# 3. 生成迁移
alembic revision --autogenerate -m "创建用户档案表"

# 4. 应用迁移
alembic upgrade head
```

### 场景 5：删除字段

```python
# 1. 删除模型中的字段定义
class Users(Base):
    # old_field 已删除

# 2. 生成迁移
alembic revision --autogenerate -m "删除旧字段"

# 3. 检查迁移脚本，确认会执行 DROP COLUMN
# 4. 应用迁移
alembic upgrade head
```

## 🔄 部署流程

### 开发环境

```bash
# 1. 修改模型代码
# 2. 生成迁移脚本
alembic revision --autogenerate -m "描述你的修改"

# 3. 测试迁移
alembic upgrade head
alembic downgrade -1  # 测试回滚
alembic upgrade head  # 恢复

# 4. 提交代码
git add migrations/versions/xxxx.py src/storage/database/shared/model.py
git commit -m "feat: xxx"
git push
```

### 生产环境部署

```bash
# 1. 拉取最新代码
git pull

# 2. 应用数据库迁移
alembic upgrade head

# 3. 部署代码（重启服务）
# ...
```

## ⚠️ 注意事项

### 1. 重要数据操作

如果你要删除字段或表，**务必先备份数据**：

```bash
# 备份数据库
pg_dump -U username dbname > backup.sql

# 或使用导出工具导出关键数据
```

### 2. 外键约束

如果有外键约束，修改表结构时要特别注意：

```python
# 正确顺序：先删除外键，再修改表结构，最后重建外键
def upgrade() -> None:
    op.drop_constraint('history_user_id_fkey', 'history', type_='foreignkey')
    op.alter_column('users', 'user_id', type_=sa.String(10))
    op.create_foreign_key('history_user_id_fkey', 'history', 'users', ['user_id'], ['user_id'])
```

### 3. 数据迁移

如果需要迁移现有数据，可以在 `upgrade()` 函数中添加数据迁移逻辑：

```python
def upgrade() -> None:
    # 1. 添加新字段
    op.add_column('users', sa.Column('nickname', sa.String(100), nullable=True))

    # 2. 迁移数据（将 username 复制到 nickname）
    from sqlalchemy import text
    op.execute(text("UPDATE users SET nickname = username"))

    # 3. 修改字段为必填（可选）
    op.alter_column('users', 'nickname', nullable=False)
```

### 4. 团队协作

- **不要修改已提交的迁移脚本**：如果发现已提交的迁移脚本有问题，创建一个新的迁移脚本来修复
- **及时同步**：团队成员拉取代码后，第一时间执行 `alembic upgrade head`
- **测试迁移**：在开发环境充分测试迁移和回滚，确保万无一失

## 🛠️ 常见问题

### Q1: 提示 "Database is locked" 或迁移失败

```bash
# 检查当前状态
alembic current

# 如果有迁移正在执行，等待或重启数据库连接

# 如果状态不一致，可以强制标记
alembic stamp head  # 强制标记为最新版本（谨慎使用！）
```

### Q2: 检测到大量差异，但实际上没有修改

```bash
# 删除错误的迁移脚本
rm migrations/versions/xxxx.py

# 检查 env.py 中的模型导入是否正确
# 确保所有模型都已导入

# 重新生成
alembic revision --autogenerate -m "xxx"
```

### Q3: 如何回滚已部署的迁移？

```bash
# 回滚到指定版本
alembic downgrade 000000000000

# 如果迁移脚本有问题，修复后重新生成新脚本
# 不要直接修改已部署的迁移脚本
```

### Q4: autogenerate 没有检测到我的修改？

- 检查 `migrations/env.py` 中是否导入了所有模型
- 检查模型定义是否正确（使用 `Mapped` 类型）
- 确保修改后保存了文件

## 📚 参考资料

- [Alembic 官方文档](https://alembic.sqlalchemy.org/)
- [SQLAlchemy 官方文档](https://docs.sqlalchemy.org/)
- [Alembic 教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

## 📞 获取帮助

如果遇到问题：

1. 查看日志：`alembic upgrade head` 会输出详细日志
2. 检查数据库：`SELECT * FROM alembic_version;`
3. 查看迁移脚本：`migrations/versions/`
4. 联系团队技术负责人

---

**记住**： Alembic 是你数据库的"时光机"，谨慎操作，充分测试！
