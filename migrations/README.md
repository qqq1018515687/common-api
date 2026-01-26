# 数据库迁移目录

## 📂 目录结构

```
migrations/
├── versions/              # 迁移脚本目录
│   └── 000000000000_初始数据库状态.py
├── env.py                 # Alembic 环境配置
├── script.py.mako         # 迁移脚本模板
└── README.md              # 本文件
```

## 🚀 常用命令

### 查看状态
```bash
# 查看当前版本
alembic current

# 查看所有迁移历史
alembic history

# 查看待执行的迁移
alembic check
```

### 创建迁移
```bash
# 自动生成迁移脚本
alembic revision --autogenerate -m "描述你的修改"

# 手动创建空白迁移脚本
alembic revision -m "手动迁移"
```

### 执行迁移
```bash
# 应用所有未执行的迁移
alembic upgrade head

# 应用到指定版本
alembic upgrade 000000000000

# 回滚到上一个版本
alembic downgrade -1

# 回滚到指定版本
alembic downgrade 000000000000
```

## 📝 迁移脚本命名规范

迁移脚本文件名格式：`{revision_id}_{description}.py`

示例：
- `000000000001_添加用户昵称字段.py`
- `000000000002_修改手机号字段长度.py`
- `000000000003_添加邮箱唯一约束.py`

## ⚠️ 注意事项

1. **不要修改已提交的迁移脚本**：如果发现有问题，创建新的迁移脚本修复
2. **充分测试**：在开发环境测试迁移和回滚后再部署
3. **备份数据**：删除表或字段前务必备份数据
4. **团队协作**：团队成员拉取代码后及时执行 `alembic upgrade head`

## 📚 详细文档

查看完整使用指南：[docs/ALEMBIC_GUIDE.md](../docs/ALEMBIC_GUIDE.md)
