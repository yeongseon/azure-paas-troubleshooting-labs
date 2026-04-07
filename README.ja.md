# Azure PaaS トラブルシューティング ラボ

[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-paas-troubleshooting-labs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read this in: [English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

**Azure App Service、Azure Functions、Azure Container Apps のためのサポートエンジニアスタイルのトラブルシューティング実験**

By Yeongseon Choe

---

## このプロジェクトが存在する理由

公式の Azure ドキュメントは正確ですが、実際のサポートシナリオで発生するすべてのエッジケースをカバーしているわけではありません。一般的なギャップ：

- **障害モードの再現** — ドキュメントの説明を超えて、特定の障害条件が実際にどのように現れるか
- **プラットフォーム vs アプリケーションの境界** — 問題が Azure インフラストラクチャで発生しているか、顧客のアプリケーションコードで発生しているかの判断
- **誤解を招くメトリクス** — ある根本原因を示唆しているが、実際には別のものを示すシグナル
- **エビデンスの校正** — 確信を持って述べられることと、追加データが必要なことを知ること

このリポジトリは、仮説駆動の実験を通じてこれらのギャップを埋めます。各実験は特定のシナリオを再現し、観察結果を記録し、明示的な信頼レベルで結果を解釈します。

これは実用ガイドではなく、チュートリアルではなく、Microsoft Learn の代替品ではありません。

## カバー内容

### App Service

- **メモリプレッシャー** — プランレベルのパフォーマンス低下、スワップスラッシング、カーネルページ回収の影響
- **procfs の解釈** — Linux コンテナ内の /proc データの信頼性と限界
- **遅いリクエスト** — フロントエンドタイムアウト vs ワーカー側の遅延 vs 依存関係のレイテンシ
- **Zip Deploy vs Container** — デプロイ方法間の動作の違い

### Functions

- **Flex Consumption Storage** — ストレージ ID の誤設定エッジケース
- **Cold Start** — 依存関係の初期化、ホストの起動シーケンス、コールドスタート期間の内訳
- **依存関係の可視性** — 利用可能なテレメトリを通じてアウトバウンド依存関係の動作を観察する限界

### Container Apps

- **Ingress SNI / Host Header** — SNI とホストヘッダーのルーティング動作、カスタムドメインのエッジケース
- **Private Endpoint FQDN vs IP** — FQDN と直接 IP アクセス間の動作の違い
- **Startup Probes** — startup、readiness、liveness プローブ間の相互作用

## エビデンスモデル

すべての実験は、校正されたエビデンスレベルで結果にタグを付けます：

| タグ | 意味 |
|-----|---------|
| **Observed** | ログ、メトリクス、またはシステム動作で直接観察された |
| **Measured** | 特定の値で定量的に確認された |
| **Correlated** | 2つのシグナルが一緒に動いた；因果関係は確立されていない |
| **Inferred** | 観察から導き出された合理的な結論 |
| **Strongly Suggested** | 強力な証拠だが、決定的ではない |
| **Not Proven** | 仮説がテストされたが確認されなかった |
| **Unknown** | データ不足 |

## ライセンス

MIT
