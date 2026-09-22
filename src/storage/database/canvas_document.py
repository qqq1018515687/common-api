"""Strict durable document contract. Signed URLs never belong in a document."""
import json
import math


def validate_document(document):
    if not isinstance(document, dict) or document.get('schemaVersion') != 1:
        raise ValueError('无效画布文档版本')
    if len(json.dumps(document, ensure_ascii=False).encode()) > 4 * 1024 * 1024:
        raise ValueError('画布文档过大')
    receipts = document.get('importedRunIds', [])
    if not isinstance(receipts, list) or len(receipts) > 20000 or any(not isinstance(item, str) or len(item) > 64 for item in receipts):
        raise ValueError('无效结果导入记录')
    nodes, edges = document.get('nodes'), document.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list) or len(nodes) > 2000 or len(edges) > 4000:
        raise ValueError('画布节点或连线超出限制')
    ids, parents, assets = set(), {}, set()
    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    def position(value):
        return isinstance(value, dict) and number(value.get('x')) and number(value.get('y'))
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('id'), str) or not 0 < len(node['id']) <= 64 or node['id'] in ids:
            raise ValueError('节点标识重复或无效')
        ids.add(node['id'])
        if node.get('type') not in ('asset', 'operation', 'group', 'note') or not position(node.get('position')):
            raise ValueError('无效节点类型或坐标')
        data = node.get('data')
        if not isinstance(data, dict):
            raise ValueError('无效节点数据')
        if node['type'] == 'asset':
            if not isinstance(data.get('assetId'), str):
                raise ValueError('素材节点需要稳定资产引用')
            assets.add(data['assetId'])
        if node.get('parentId'):
            parents[node['id']] = node['parentId']
    for child, parent in parents.items():
        seen = {child}
        while parent:
            if parent not in ids or parent in seen:
                raise ValueError('分组关系无效')
            seen.add(parent)
            parent = parents.get(parent)
    edge_ids = set()
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get('id'), str) or edge['id'] in edge_ids or edge.get('source') not in ids or edge.get('target') not in ids or edge['source'] == edge['target']:
            raise ValueError('无效连线')
        edge_ids.add(edge['id'])
    viewport = document.get('viewport')
    if not position(viewport) or not number(viewport.get('zoom')) or not 0.05 <= viewport['zoom'] <= 4:
        raise ValueError('无效视口')
    def no_urls(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in ('url', 'signedurl', 'previewurl', 'objectkey', 'fileurl'):
                    raise ValueError('文档只能保存 assetId，不能保存访问地址')
                no_urls(item)
        elif isinstance(value, list):
            for item in value:
                no_urls(item)
    no_urls(document)
    return assets
