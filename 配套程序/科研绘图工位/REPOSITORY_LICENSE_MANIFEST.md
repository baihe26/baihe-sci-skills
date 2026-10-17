# 配套来源与许可

EditaPlot runtime：hang-jin/editaplot，固定上游 01721038afd212103d96225319b22d1bbfe32270，Apache-2.0。保留 vendor/editaplot 的 LICENSE、NOTICE、AUTHORS.md 和 THIRD_PARTY_NOTICES.md；本分发含此前适配的运行时，非上游原样发行。

Nature figure QA：原有上游固定 84880815fb37317b3766bff2c2abba395b8993c3，Apache-2.0，保留 vendor/nature_qa/LICENSE。两个原检查脚本按已有许可提供，不附论文图片或来源PDF。

originpro、OriginExt 与其Python依赖由安装程序从PyPI按哈希获取，各自许可保留在安装后的包元数据中。Origin商业软件和许可不分发。

PyMuPDF 使用 AGPL-3.0 或 Artifex 商业许可；本源码包不捆绑其二进制，安装时直接取得上游分发。它不是MIT/Apache依赖。若将环境、应用或服务对外再分发，应按实际使用方式评估该依赖的许可义务，不能用本仓库的使用许可覆盖它。
