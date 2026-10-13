# ZEEKR 澳洲市场监控（zeekr-watch）

静态网页 + GitHub Actions 定时抓取（每 30 分钟）。监控三类内容，均围绕现行 ZEEKR 车型（X、7X、009，以及待上市的 007 GT / 8X / 9X）：

1. **投诉监控** — Google News（含 Whirlpool / Drive / CarsGuide 等被反爬站点的索引）、Reddit（r/Zeekr7xAustralia、r/ZeekrAustraliaNZ、r/Zeekr、r/CarsAustralia、r/AustralianEV 等）、ProductReview.com.au、OzBargain、App Store / Google Play 的 ZEEKR app 评价、政府召回库、Google 地图门店评价（需 API key）。
2. **竞品上市** — CarExpert / The Driven / EV Central / Chasing Cars / WhichCar 的 RSS 与 Google News，按 `config/competitors.json` 里的竞品名单匹配，识别 launch / price_cut / price_rise / offer 信号。
3. **竞品价格与销售政策** — 人工核定的基准价目与政策（`config/competitors.json`），叠加新闻信号，并对各品牌官网 offers 页面做快照比对，页面文字变化会进入"官网政策页面变化记录"。

## 目录

```
config/zeekr_models.json   ZEEKR 车型、版本、RRP（万元 × 10,000）
config/competitors.json    竞品集（tier: core / reference / watch）、版本价格、现行政策、来源链接、对标说明
config/sources.json        抓取源：Google News 查询、RSS、Reddit 子版、品牌政策页、门店名单
monitor/                   Python 抓取程序（run.py 为入口）
docs/index.html            网站（中/英切换，深色模式）
docs/data/                 抓取结果（items.json、summary.json、offer_changes.json、places.json …）
.github/workflows/monitor.yml   每 30 分钟运行
```

## 部署

1. 推送到 GitHub 仓库 `main` 分支。
2. Settings → Pages → Build and deployment：Source = **Deploy from a branch**，Branch = **main** / **/docs**。
3. Settings → Actions → General → Workflow permissions：**Read and write permissions**。
4. Actions → "ZEEKR market watch" → **Run workflow** 跑一次。
5. 访问 `https://<用户名>.github.io/zeekr-watch/`。

可选 Secrets（Settings → Secrets and variables → Actions）：

| Secret | 用途 |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Google 地图门店评价（Places API New；每 6 小时一次，17 家门店，月成本约 US$30–40，在 US$200 免费额度内） |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit 官方 API（在 reddit.com/prefs/apps 建 script app），避免匿名抓取 429 |

## 维护

- **更新竞品基准价/政策**：编辑 `config/competitors.json`，提交即可；网站直接读取。
- **增删竞品**：同上，`zeekr` 字段写对应 ZEEKR 车型 key（X / 7X / 009 / 7GT / 8X / 9X）。
- **调整关键词规则**：`monitor/classify.py`（投诉分类、负面词、上市/价格信号词）。
- **本地运行**：`pip install -r requirements.txt && python -m monitor.run`（可加 `--skip reddit,offers`）。
- 数据保留 180 天；GitHub 对 60 天无提交的公开仓库会自动停用定时任务，数据每 30 分钟提交一次，正常不会触发。

## 已知限制

- Whirlpool、Drive、CarsGuide、carsales 车主评价、Trustpilot 对数据中心 IP 返回 403，只能通过 Google News 索引间接覆盖（有天级延迟）。
- Facebook 公开 group 无法抓取；官方 Page 评论需 Page access token。
- Google Places 每个门店每次只返回最新 5 条评价。
- 分类为关键词规则，存在误判；重要事项请点开原文核对。
