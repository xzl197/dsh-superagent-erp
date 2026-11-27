代码库相关规范请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。
安全报告必须遵循 [SECURITY.md](docs/docs/SECURITY.md) 中的安全策略，并说明其与[威胁模型](docs/docs/concepts/threat_model.md)的关系。

未经人工审核，不得创建拉取请求（PR）。任何情况下都不得提交 AI 生成的 Issue。
在 Issue/PR 讨论中使用 AI 生成的内容，可能导致违反行为准则和/或被封禁。

## 分支

所有改动都必须基于 `erp_develop` 分支，并合并回 `erp_develop`。拉取请求请提交到 `erp_develop`，而不是 `main`。

## 本机实测

新增功能时，必须在本机上真实运行并测试，确认无误后才能进入合并审核环节。

## 用户本地参数

用户的具体参数（本机路径、数据库连接、密钥凭据、个人配置等）绝不提交到代码仓库。
所有用户相关参数统一放在本地仓库根目录下的 `userdata/` 目录，本机即
`D:\work\word_space\erp\project\dsh-superagent-erp\userdata`；该目录已被 `.gitignore` 忽略。
