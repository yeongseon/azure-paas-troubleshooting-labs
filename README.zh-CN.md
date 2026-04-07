# Azure PaaS 故障排除实验室

[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-paas-troubleshooting-labs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read this in: [English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md)

**面向 Azure App Service、Azure Functions 和 Azure Container Apps 的支持工程师风格故障排除实验**

By Yeongseon Choe

---

## 为什么存在这个项目

官方 Azure 文档是准确的，但并未涵盖实际支持场景中出现的所有边缘情况。常见的差距包括：

- **故障模式重现** — 特定故障条件实际如何表现，超出文档描述的范围
- **平台与应用程序边界** — 确定问题是源于 Azure 基础架构还是客户应用程序代码
- **误导性指标** — 暗示一个根本原因但实际指向另一个原因的信号
- **证据校准** — 知道什么可以有把握地陈述，什么需要额外数据

本仓库通过假设驱动的实验来填补这些差距。每个实验重现特定场景，记录观察结果，并以明确的置信水平解释结果。

这不是实用指南，不是教程，也不是 Microsoft Learn 的替代品。

## 涵盖内容

### App Service

- **内存压力** — 计划级别性能下降、交换抖动、内核页面回收效应
- **procfs 解释** — Linux 容器内 /proc 数据的可靠性和限制
- **慢请求** — 前端超时 vs 工作进程端延迟 vs 依赖项延迟
- **Zip Deploy vs Container** — 部署方法之间的行为差异

### Functions

- **Flex Consumption Storage** — 存储标识配置错误的边缘情况
- **Cold Start** — 依赖项初始化、主机启动顺序、冷启动持续时间分解
- **依赖项可见性** — 通过可用遥测观察出站依赖项行为的限制

### Container Apps

- **Ingress SNI / Host Header** — SNI 和主机头路由行为、自定义域边缘情况
- **Private Endpoint FQDN vs IP** — FQDN 和直接 IP 访问之间的行为差异
- **Startup Probes** — startup、readiness 和 liveness 探针之间的交互

## 证据模型

所有实验都使用校准的证据级别标记其发现：

| 标签 | 含义 |
|-----|---------|
| **Observed** | 在日志、指标或系统行为中直接观察到 |
| **Measured** | 用特定值定量确认 |
| **Correlated** | 两个信号一起移动；因果关系未建立 |
| **Inferred** | 从观察中得出的合理结论 |
| **Strongly Suggested** | 强有力的证据，但不是决定性的 |
| **Not Proven** | 假设已测试但未得到确认 |
| **Unknown** | 数据不足 |

## 许可证

MIT
