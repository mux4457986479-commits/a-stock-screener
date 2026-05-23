# A股低价股筛选 GitHub Pages 版

这个版本用于长期给领导收藏访问：

- `index.html`：领导打开的页面；
- `data.json`：最新筛选结果；
- `scripts/update_data.py`：读取东方财富数据并生成 `data.json`；
- `.github/workflows/update-low-price.yml`：GitHub Actions 定时更新。

## 部署

1. 在 GitHub 新建公开仓库，例如 `a-stock-screener`。
2. 上传本目录里的所有文件到仓库根目录。
3. 打开仓库 `Settings -> Pages`。
4. Source 选择 `Deploy from a branch`。
5. Branch 选择 `main`，目录选择 `/root`。
6. 打开 `Actions`，手动运行一次 `Update A-share low price data`。
7. 等 Pages 发布完成，把 Pages 链接发给领导收藏。

链接格式类似：

```text
https://你的用户名.github.io/a-stock-screener/
```

## 为什么更稳

手机页面不再直接请求东方财富，而是读取同站点的 `data.json`。
东方财富读取工作由 GitHub Actions 定时完成。
如果某次更新失败，脚本会保留最近一次成功数据，并在页面提示失败原因。

## 定时规则

默认工作日北京时间 09:00 到 15:30 左右，每 30 分钟更新一次。

GitHub Actions 使用 UTC 时间，配置在：

```text
.github/workflows/update-low-price.yml
```

## 注意

本页面只供研究参考，不构成投资建议。低价股风险高，需结合基本面、流动性和公告风险判断。
