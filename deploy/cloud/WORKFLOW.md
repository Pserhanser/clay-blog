# 个人博客开发与发布流程

## 当前状态与授权

- 仓库已存在：<https://github.com/Pserhanser/clay-blog>；本地 origin 已指向它。
- 当前本地含有尚未提交的博客定制内容，不能把 GitHub 的旧模板直接覆盖到线上。
- 本次仅准备本地 CI/CD、发布脚本和协作规则。未 commit、push、创建 PR、合并、安装服务器脚本、配置 GitHub secrets 或更改线上发布。
- 新流程未启用前，线上继续运行现有版本。

## 日常更新

1. 默认只在本地修改、预览、审阅差异。运行 `npm test`、`python3 -m unittest discover -s tests -p 'test_*.py'` 和 `SITE_URL=https://hanser.fireemblem.top npm run build`。
2. 仅在用户明确说“提交PR”后，才核对远程 main、创建功能分支、commit、push 并创建 PR。首次 PR 必须包含现有博客全部定制内容，审查资源文件与隐私信息。
3. PR 自动运行依赖安装、单元测试、发布保留策略测试和生产构建。
4. 提交 PR 不等于合并授权。用户另行明确要求合并后才合并；禁止直接 push main。
5. main 检查通过后，部署任务经博客专用受限 SSH 密钥运行服务器发布脚本。
6. 服务器只部署 CI 指定且与 origin/main 一致的完整 SHA；限内存/CPU 构建、原子切换、健康检查，失败回滚。

## 首次启用（待授权，不自动执行）

- 服务器 Git 缓存：`/home/ubuntu/hanser-blog-ci/application`，origin 指向个人博客仓库；不要复用 fefw 的代码缓存。
- 服务器控制脚本：将本目录下 `server-deploy.sh` 和 `prune-releases.py` 审阅后安装至 `/usr/local/lib/hanser-blog/`，由 root 拥有且普通用户不可写，shell 脚本可执行。
- 为博客单独创建 SSH 部署密钥。authorized_keys 设置 `command="/usr/local/lib/hanser-blog/server-deploy.sh",restrict`；保留主机指纹校验，不复用或扩大 fefw 的受限密钥权限。
- 发布脚本按现有 ubuntu 管理账号运行，需 Docker、Python 3.10+、Git、curl 和对博客发布目录的受控 sudo 权限。先核验权限，再启用；不要因为缺失权限而取消密钥限制。
- GitHub production environment 配置 `DEPLOY_HOST`、`DEPLOY_SSH_KEY`、`DEPLOY_KNOWN_HOSTS`。推荐启用生产环境审批和 main 分支保护，要求 PR 和 check 通过；尚未远程配置，不能认为已强制生效。
- 先测试受限命令、首次健康检查及回滚，获准发布后设置仓库变量 `PRODUCTION_DEPLOY_ENABLED=true`；默认缺省时不会自动部署。
- 应用发布不会更新 `/usr/local/lib/hanser-blog/` 中的控制脚本；其变动需单独审阅安装。
- 私有流量后台引入 `site/ + server/` 发布布局，启用前还必须按 `docs/private-analytics.md` 审阅安装后台服务、正式管理员和 Nginx 路由，完成首次布局迁移。全部核验且获准后才创建服务器 `hanser-blog-ci/ANALYTICS_READY` 标记；未完成时新版发布脚本主动停止，避免旧布局被误切换。

## 保留与回滚

- 博客发布根目录：`/var/www/hanser.fireemblem.top`。
- `current` 为当前发布目录的符号链接；正式页面来自 `current`。
- `releases` 最多保留 **3 个发布版本：当前版 + 2 个历史回滚版本**。
- 只有新版本健康检查成功后才清理，优先保留当前版、刚才的健康版，再保留最近的一个版本。
- 失败构建不进入发布目录；失败健康检查恢复旧链接并移除失败版本，不清理健康备份。
- `prune-releases.py` 默认只打印待清理目录，只有 `--apply` 才执行删除；不会跟随 releases 内的外部符号链接。
- 已有云端历史目录本次未清理。待部署流程获准安装并成功发布后，才按此规则收敛至 3 个。

## 与 fefw 隔离

不修改 fefw 的数据库、共享媒体、容器、站点配置、仓库缓存或部署密钥。博客静态构建使用单独的临时容器，内存 1 GiB、内存加交换 2 GiB、CPU 1 核。博客通过已有 Nginx current 链接发布，不需重启 fefw 服务。
