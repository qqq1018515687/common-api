# 旧数据清理 - 快速参考

## 一键清理命令

```bash
# 第一步：分析
python scripts/clean_old_data.py --analyze

# 第二步：试运行
python scripts/clean_old_data.py --cleanup

# 第三步：确认后执行
python scripts/clean_old_data.py --cleanup --force
```

---

## 文件识别规则

| 文件名 | 是否保留 | 原因 |
|-------|---------|------|
| `avatar_123.png` | ✅ 保留 | 文件名包含 avatar |
| `user_avatar_456.jpg` | ✅ 保留 | 文件名包含 avatar |
| `upload_789.png` | ❌ 删除 | 旧数据，非头像 |
| `temp_012.bin` | ❌ 删除 | 旧数据，非头像 |
| `avatars/new_avatar.png` | ✅ 不受影响 | 新数据，已有分类前缀 |
| `uploads/upload_345.png` | ✅ 不受影响 | 新数据，已有分类前缀 |

---

## 安全检查

- [ ] 已执行 `--analyze`，查看旧文件统计
- [ ] 已执行 `--cleanup`（试运行），查看删除列表
- [ ] 确认头像文件识别正确
- [ ] 确认其他文件可以删除
- [ ] 如有重要文件，先备份

---

## 详细文档

- 完整指南：`docs/CLEAN_OLD_DATA_GUIDE.md`
- 常见问题：`docs/STORAGE_SUMMARY.md`
- 对比说明：`docs/OLD_VS_NEW_DATA.md`

---

## 常见问题

**Q: 头像会被误删吗？**
A: 不会。只要文件名包含 `avatar`，就会被保留。

**Q: 新数据会被删除吗？**
A: 不会。新数据有分类前缀（avatars/、uploads/、temp/），不受影响。

**Q: 删除后能恢复吗？**
A: 不能。请先试运行，确认无误后再执行。

**Q: 清理失败怎么办？**
A: 查看日志，失败的文件会被列出，可以重新执行清理。

---

## 紧急停止

如果发现正在删除的文件中有误，立即：

1. 停止当前进程（Ctrl+C）
2. 检查已删除的文件列表
3. 如果有误删，联系存储服务商寻求恢复

---

## 快速示例

```bash
# 示例 1：快速清理（推荐流程）
$ python scripts/clean_old_data.py --analyze
总旧文件数: 150
头像文件: 20 (2.5 MB)
其他文件: 130 (5.8 MB)

$ python scripts/clean_old_data.py --cleanup
将要处理的文件:
  头像文件（保留）: 20
  其他文件（删除）: 130 (5.8 MB)

$ python scripts/clean_old_data.py --cleanup --force
确认继续清理？(yes/no): yes
清理完成！释放空间: 5.8 MB

# 示例 2：详细查看
$ python scripts/clean_old_data.py --analyze --verbose
头像文件列表:
  ✓ avatar_abc123.png (125.5 KB)
  ✓ avatar_def456.jpg (234.2 KB)

其他文件列表（将被删除）:
  ✗ upload_ghi789.png (45.2 KB)
  ✗ temp_jkl012.bin (12.1 KB)
```

---

## 备份建议

如果不确定，可以：

1. **备份重要文件**
   ```bash
   # 手动下载重要文件到本地
   ```

2. **先清理部分文件**
   - 修改脚本，只删除特定前缀的文件
   - 分批清理，降低风险

3. **联系技术支持**
   - 如果不确定，先咨询技术支持
   - 获取专业的清理建议

---

**记住：先试运行，再执行！**
