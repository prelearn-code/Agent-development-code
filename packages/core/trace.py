"""事件的本地存储：TraceWriter 的落点（04 段剩余任务里实现）。

约定：Trace 只记"发生了什么"的结构化事件（run_id / step / outcome / 耗时 / 拒绝原因），
不记文件全文、密钥、口令；写入前统一走 `packages.core.logging.scrub`。
"""
