# vps-deals · 官方 VPS 价格与优惠雷达

默认输入：NICHE=`VPS hosting`，BRAND=`vps-deals`。种子为 BuyVM、RamNode、RackNerd 官方公开页面。独立中文价格索引；促销与常规定价分开，未知库存、税费、续费价和有效日期不补造。

- 仓库：https://github.com/holaclea/vps-deals-promo-radar
- 主站：待 Cloudflare Pages 部署核验后填写，当前不声称已上线。
- 数据来源：`config.json` 中的官方 URL；每条记录带核验时间、原价片段和响应 SHA-256。
- 当前联盟追踪：未启用。没有获批的联盟 ID，不编造链接或佣金。

## 运行

Python 3.11+，仅标准库，无 pip 安装，无推理或第三方数据 API 密钥。

```sh
python scraper.py
python build.py
python -m unittest discover -s tests -v
python -m http.server 8000 --directory site
```

`scraper.py` 尊重 robots.txt，只读取固定种子价格页。403/429 不绕过；临时网络失败最多重试一次；原子写入数据。格式变化会报错而不是猜价格。源失败保留旧记录并标 stale；正常源中消失的套餐从当前快照移除。Git 历史保存旧记录，不存整页版权内容。

## 自动更新

`.github/workflows/update.yml` 每天北京时间 02:23（UTC 18:23）运行，并支持手动触发。真实采集时间和失败状态也作为数据提交。公开仓库的标准 GitHub 托管 runner 在相应免费政策内运行；这不是刷提交保活。

GitHub 自动发放、短期有效的 `GITHUB_TOKEN` 只获 `contents: write`，用于提交 `data/` 和 `site/`。无需用户添加 PAT Secret。首次建仓凭证不参与日常运行。GitHub Actions 基础设施步骤使用官方 checkout/setup-python action；业务抓取与构建完全是 Python。浏览器仅有一个本地日期提示脚本，不调 API。

Cloudflare Pages 使用 Git 集成监听主分支。必须实测 Actions 自动提交后的 Pages 部署；不能把本地成功当作自动部署成功。GitHub token 不触发另一个 Actions workflow，但 Cloudflare Git 集成是外部集成，不应混同 GitHub Pages。

全部来源失败时，仍构建并提交带旧数据警告的页面，然后把 workflow 标记失败。部分失败写 Actions warning 和摘要。平台调度可能延迟；60 天无仓库活动的公开仓库定时 workflow 可能停用。不要承诺永不维护。平台通知设置由账号控制。

## Cloudflare Pages 配置

1. Workers & Pages → 创建 Pages → 导入本仓库。GitHub App 只授权本仓库。
2. Production branch: `main`；Framework preset: None。
3. Build command: `python build.py`；Build output directory: `site`；Root: 仓库根目录。
4. Python 版本选 3.12。配置无需 Cloudflare API token。
5. 部署后把真实 production origin 写入 `config.json` 的 `base_url` 并重新提交。构建也支持 Cloudflare 的 `CF_PAGES_URL`，但稳定的生产 URL 优先。
6. 核验首页、商家、详情、对比、JSON、robots/sitemap；手动运行一次更新，核对随后 Pages 部署的 commit SHA。

免费计划仍受构建次数、资源量及平台规则限制。每日一次通常约 30 次/月；开发提交会增加构建次数。

## 变现与退出

详见 [MONETIZATION.md](MONETIZATION.md)。真实联盟链接按 offer ID 配置：

```json
{"affiliate_links":{"真实offer-id":{"approved":true,"url":"从联盟后台获取的真实HTTPS链接"}}}
```

不填时直达官方来源。配置后详情页自动披露并添加 `rel=sponsored`；不改变价格排序。计划价格不保证用户留存，管理型主机是否合适应按服务与用户需求判断。

## 运营边界

域名可在品牌确定后注册，保留品牌和连续经营记录；仅放着域名攒年份不保证排名。本站尚未验证搜索需求、竞争难度或盈利能力。提供有来源的数据和可复用对比，争取别人自愿引用；不购买操纵排名的链接，不制造评价或流量。

官方规则参考（2026-09-09核对）：
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/concepts/security/github_token
- https://developers.cloudflare.com/pages/get-started/git-integration/
- https://developers.cloudflare.com/pages/platform/limits/

如果数据源改变页面结构，需修改对应解析器并测试。无外部依赖不等于免维护。
