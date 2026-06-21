# data

这里用于放本地知识库数据库或索引文件的说明。

真实数据库文件默认不提交到 Git：

- `*.db`
- `*.duckdb`
- `*.sqlite`

当前系统优先使用 `.autogis/training_reflection_index.json` 做轻量索引。后续如果训练反思规模扩大，可以在这里记录 DuckDB 表结构和迁移脚本。
