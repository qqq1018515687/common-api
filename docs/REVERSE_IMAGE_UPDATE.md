# Reverse Image Node 更新说明

## 更新内容

`reverse_image_node` 节点已更新，现在支持**多张图片输入**，而不仅仅是单张图片。

## 修改前

### 输入
```python
class ReverseImageInput(BaseModel):
    file: Optional[File] = Field(default=None, description="图像文件")
```

### 请求示例
```json
{
  "call_type": "tool",
  "tool_type": "reverse_image",
  "input": {
    "file": {
      "url": "https://example.com/image.jpg",
      "file_type": "image"
    }
  }
}
```

## 修改后

### 输入
```python
class ReverseImageInput(BaseModel):
    file_list: Optional[List[File]] = Field(default=None, description="图像文件列表")
```

### 请求示例（单张图片）
```json
{
  "call_type": "tool",
  "tool_type": "reverse_image",
  "input": {
    "file_list": [
      {
        "url": "https://example.com/image.jpg",
        "file_type": "image"
      }
    ]
  }
}
```

### 请求示例（多张图片）
```json
{
  "call_type": "tool",
  "tool_type": "reverse_image",
  "input": {
    "file_list": [
      {
        "url": "https://example.com/image1.jpg",
        "file_type": "image"
      },
      {
        "url": "https://example.com/image2.jpg",
        "file_type": "image"
      },
      {
        "url": "https://example.com/image3.jpg",
        "file_type": "image"
      }
    ]
  }
}
```

## 功能特性

1. **支持多图片分析**：可以同时分析多张图片，生成综合提示词
2. **兼容单图片**：仍然支持单张图片输入（传入长度为 1 的列表）
3. **错误处理**：如果未提供图片或文件列表为空，会返回错误信息

## 实现细节

节点内部会遍历 `file_list`，为每张图片构造 `image_url` 内容，然后一次性发送给多模态模型进行分析。

```python
content_list = [{"type": "text", "text": user_prompt_content}]

# 添加所有图片
for file_item in state.file_list:
    content_list.append({
        "type": "image_url",
        "image_url": {"url": file_item.url}
    })

messages = [
    SystemMessage(content=system_prompt_content),
    HumanMessage(content=content_list)
]
```

## 测试结果

✅ 多张图片输入：成功生成提示词
✅ 单张图片输入：成功生成提示词
✅ 空文件列表：正确返回错误信息
