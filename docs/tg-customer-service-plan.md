# TG 多账号客服管理系统策划文档

## 1. 项目背景

业务方希望搭建一套基于 Telegram 账号的客户触达与回复管理系统，用于统一管理多个 TG 账号、批量导入已有客户手机号、将客户分配给不同账号进行首次沟通，并在网页后台集中查看客户是否回复、是否已读、是否未回复以及账号是否异常。

系统应服务于客服管理场景，而不是无差别群发场景。产品设计需要默认面向已授权、已有业务关系或已明确同意被联系的客户，并保留导入来源、授权状态、发送记录和操作日志。

## 2. 核心目标

1. 支持多个 TG 账号集中接入和管理。
2. 支持通过 ZIP 包导入 Telegram session 文件。
3. 支持客户手机号数据批量导入、去重、标记来源和授权状态。
4. 支持按规则将客户分配给不同 TG 账号。
5. 支持配置打招呼消息模板。
6. 支持创建批量触达任务，并跟踪发送结果。
7. 支持收集客户回复，并区分以下状态：
   - 已回复
   - 已读未回复
   - 未读/未触达
   - 发送失败
8. 支持查看每个账号的发送量、回复量、失败量和异常状态。
9. 支持账号分组管理，每个 TG 账号必须归属至少一个账号分组。
10. 支持给客服人员配置可使用的账号分组，客服只能查看和操作授权范围内的账号、好友、客户与聊天。
11. 支持批量群发任务，任务可选择客户数据、好友数据或指定分组作为发送对象。
12. 支持设置每条消息的发送间隔、随机间隔、失败后间隔、账号并发数和任务暂停/继续。
13. 支持网络代理管理，可为 TG 账号绑定固定代理或从代理池分配代理，用于账号登录、发送和监听。

## 3. 使用角色

### 3.1 管理员

负责导入 TG 账号、配置系统参数、管理客服账号状态、查看全局数据和处理异常。

### 3.2 客服主管

负责导入客户数据、配置消息模板、创建触达任务、查看回复转化和账号效率。

### 3.3 客服人员

负责查看分配到账号下的客户回复，跟进客户对话，标记处理状态。

### 3.4 系统 Worker

非人工角色，负责执行发送队列、监听回复、同步账号状态、统计任务数据和触发异常熔断。

## 4. 产品范围

### 4.1 首期范围

首期建议先完成可闭环的管理后台：

1. TG 账号 session 导入。
2. TG 账号列表与状态管理。
3. 客户手机号批量导入。
4. 客户数据去重、来源、标签、授权状态管理。
5. 客户分配规则。
6. 消息模板管理。
7. 触达任务创建。
8. 发送状态跟踪。
9. 回复状态聚合看板。
10. 基础操作日志。
11. 账号分组管理。
12. 客服人员与账号分组授权。
13. 群发任务创建与发送间隔配置。
14. 群发任务暂停、继续、取消和失败重试。
15. 网络代理池管理、账号代理绑定和代理健康检测。

### 4.2 暂不建议首期实现

以下能力复杂度较高，建议在首期流程稳定后再做：

1. 多人实时协作客服聊天窗口。
2. 完整 CRM 客户生命周期管理。
3. 复杂自动化营销流程。
4. 多渠道统一接入，例如 WhatsApp、Line、Email。
5. AI 自动回复。
6. 复杂组织架构审批流。

## 5. 核心业务流程

### 5.1 TG 账号导入流程

1. 管理员上传 ZIP 包。
2. 系统解压并识别目录结构。
3. ZIP 解压后的结构应为：

```text
userid/
  xxx.session
```

4. 系统读取一级目录名作为 TG 账号标识 `userid`。
5. 系统保存 session 文件到服务端安全目录。
6. 系统创建或更新 TG 账号记录。
7. 系统将账号标记为“待验证”。
8. 管理员为账号选择账号分组；如果未选择，则进入“未分组”默认分组，不能参与客服分配和群发任务。
9. 后续通过 Telegram API 校验 session 是否可用。

账号状态建议包括：

| 状态 | 说明 |
| --- | --- |
| 待验证 | session 已导入，但尚未完成登录校验 |
| 正常 | session 可用，账号可参与发送 |
| 暂停 | 人工暂停使用 |
| 受限 | Telegram 限制、频控或疑似风控 |
| 异常 | session 失效、登录失败或发生不可恢复错误 |

### 5.1.1 账号分组规则

账号分组是系统的核心权限边界。一个 TG 账号可以归属一个主分组，也可以根据业务需要附加多个可见分组。首期建议采用“一个账号一个主分组”的简单模型，后续再扩展多分组。

账号分组用途：

1. 控制客服人员可以使用哪些 TG 账号。
2. 控制客服人员可以看到哪些好友、客户和聊天记录。
3. 控制批量群发任务可选择的发送账号池。
4. 控制账号统计、任务统计和异常告警的聚合维度。

账号分组字段建议：

| 字段 | 说明 |
| --- | --- |
| groupName | 分组名称，例如“售前一组”“英语组”“夜班组” |
| enabled | 是否启用 |
| dailyLimit | 分组每日发送上限 |
| remark | 备注 |

### 5.1.2 账号代理规则

网络代理用于控制 TG 账号连接 Telegram 时使用的出口网络。代理必须作为账号连接配置的一部分，由系统统一管理，不能由 worker 临时随意切换。

首期建议采用“账号固定绑定代理”的策略：

1. 每个 TG 账号可以绑定 0 或 1 个网络代理。
2. 账号绑定代理后，session 校验、发送消息、监听回复都必须使用同一个代理。
3. 未绑定代理的账号使用服务器默认网络。
4. 代理不可用时，账号应进入“代理异常”或“暂停”状态，不应自动随机换代理继续发送。
5. 如需切换代理，应由管理员操作，并记录审计日志。

后续可以支持代理池自动分配，但必须遵守稳定性规则：

| 规则 | 说明 |
| --- | --- |
| 固定绑定 | 同一账号长期使用同一代理，减少登录环境频繁变化 |
| 健康检测 | 定时检测代理连通性、延迟和最近失败原因 |
| 区域匹配 | 账号国家/地区与代理出口区域尽量一致 |
| 失败暂停 | 代理连续失败达到阈值时暂停相关账号 |
| 审计记录 | 代理新增、编辑、绑定、解绑、切换均写入日志 |

### 5.2 客户导入流程

1. 客服主管上传或粘贴客户数据。
2. 系统解析手机号、姓名、标签、来源、授权状态。
3. 系统校验手机号格式。
4. 系统按手机号去重。
5. 系统只允许“已授权联系”的客户进入发送候选池。
6. 未授权客户可入库，但不能创建发送任务。

建议导入字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| phone | 是 | 客户手机号，建议国际格式 |
| name | 否 | 客户姓名 |
| tags | 否 | 客户标签，可多个 |
| source | 否 | 数据来源 |
| consent | 是 | 是否已授权联系 |
| remark | 否 | 备注 |

### 5.3 客户分配流程

1. 选择可用账号分组。
2. 系统根据当前操作人的权限过滤可用 TG 账号。
3. 选择可用 TG 账号。
4. 选择待分配客户。
5. 按规则分配客户到账号。
6. 分配完成后，客户状态变为“已分配”。

首期建议支持以下分配规则：

| 规则 | 说明 |
| --- | --- |
| 平均分配 | 按账号数量轮询分配 |
| 按账号上限分配 | 每个账号最多分配 N 个客户 |
| 排除异常账号 | 受限、暂停、异常账号不参与分配 |
| 按账号分组分配 | 只使用选中账号分组内的可用账号 |
| 按客服权限分配 | 只分配到当前客服有权限使用的账号 |

后续可扩展：

1. 按账号历史回复率分配。
2. 按客户标签分配。
3. 按地区、语言或业务线分配。
4. 按账号每日剩余额度分配。

### 5.4 消息模板流程

1. 创建消息模板。
2. 支持变量替换。
3. 创建发送任务时选择模板。
4. 系统为每个客户生成实际消息内容。

首期变量建议：

| 变量 | 示例 |
| --- | --- |
| `{name}` | 客户姓名 |
| `{phone}` | 客户手机号 |
| `{source}` | 客户来源 |

模板需要保留修改记录，避免历史任务内容被后续修改影响。

### 5.5 发送任务流程

1. 选择消息模板。
2. 选择任务类型：客户触达、好友群发、指定用户群发。
3. 选择客户范围、好友范围或导入目标数据。
4. 选择账号分组，系统根据当前操作人的权限过滤可用账号池。
5. 配置发送间隔、随机间隔、失败间隔、账号并发数和任务上限。
6. 系统检查客户是否已授权。
7. 系统检查客户是否已分配账号，或根据账号分组自动分配发送账号。
8. 系统检查账号状态、分组额度、账号每日额度和任务额度。
9. 创建发送队列。
10. 后台 worker 按频控策略逐条发送。
11. 系统记录每条消息的发送结果。
12. 系统持续监听客户回复和已读状态。

发送任务状态建议：

| 状态 | 说明 |
| --- | --- |
| 草稿 | 尚未启动 |
| 队列中 | 已创建发送队列 |
| 发送中 | worker 正在执行 |
| 已暂停 | 人工或系统暂停 |
| 已完成 | 队列处理完成 |
| 部分失败 | 存在失败记录 |
| 已取消 | 人工取消 |

### 5.5.1 群发任务类型

群发不是单一功能，程序上应拆成不同任务类型，避免后续逻辑混乱。

| 任务类型 | 发送对象 | 典型场景 | 约束 |
| --- | --- | --- | --- |
| customer_broadcast | 客户数据 | 对已授权客户发送通知或首次问候 | 必须 `consent=true` |
| friend_broadcast | 账号好友 | 对账号已有好友发送通知 | 只允许当前账号或授权账号分组好友 |
| imported_target_broadcast | 临时导入号码/用户名 | 一次性导入目标后发送 | 必须记录来源和授权状态 |
| group_member_notice | 群组成员 | 对已加入业务群的成员发送通知 | 必须是合规通知，且受平台限制 |

首期建议实现 `customer_broadcast` 和 `friend_broadcast`。其他类型可以预留表字段，不急于开放页面入口。

### 5.5.2 发送间隔配置

每个群发任务必须有独立的执行参数，不能写死在代码里。

| 参数 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| successIntervalSeconds | number | 单账号发送成功后，下一条消息的基础间隔 | 60 |
| failureIntervalSeconds | number | 单账号发送失败后，下一次尝试前等待时间 | 120 |
| randomMinSeconds | number | 随机附加间隔下限 | 10 |
| randomMaxSeconds | number | 随机附加间隔上限 | 30 |
| perAccountConcurrency | number | 单个 TG 账号同时执行的发送数，建议固定为 1 | 1 |
| taskConcurrency | number | 任务级并行账号数 | 5 |
| maxPerAccount | number | 本任务每个账号最多发送多少条 | 100 |
| maxPerDay | number | 本任务每日最多发送多少条 | 1000 |
| quietHoursStart | string | 静默时段开始 | 22:00 |
| quietHoursEnd | string | 静默时段结束 | 09:00 |

实际下一次发送时间计算：

```text
nextRunAt = now
  + successIntervalSeconds 或 failureIntervalSeconds
  + random(randomMinSeconds, randomMaxSeconds)
```

如果任务、账号或分组进入暂停状态，则队列记录不再被 worker 拉取，直到恢复后重新计算 `nextRunAt`。

### 5.5.3 群发任务生命周期

| 状态 | 说明 |
| --- | --- |
| draft | 草稿，尚未生成队列 |
| pending_review | 待审核，可选 |
| queued | 已生成队列 |
| running | 正在发送 |
| paused | 人工暂停 |
| throttled | 系统频控暂停 |
| completed | 全部处理完成 |
| partially_failed | 部分失败 |
| cancelled | 已取消 |

任务暂停后需要保留队列进度，继续时不能重复发送已成功的消息。

### 5.6 回复收集流程

1. 后台监听每个 TG 账号的对话事件。
2. 收到客户消息后，按手机号或 TG 用户标识匹配客户。
3. 更新客户状态为“已回复”。
4. 保存回复内容、回复时间、所属账号。
5. 在后台看板和客户列表中展示。

客户触达状态建议：

| 状态 | 说明 |
| --- | --- |
| 未触达 | 尚未创建发送记录 |
| 已分配 | 已分配账号，但未进入队列 |
| 队列中 | 已进入发送队列 |
| 已发送 | 消息发送成功，但未确认已读 |
| 已读未回复 | 客户已读，但未回复 |
| 已回复 | 客户已回复 |
| 发送失败 | 发送失败或不可达 |

## 6. 后台页面规划

### 6.1 总览看板

展示核心指标：

1. TG 账号总数。
2. 可用账号数。
3. 客户总数。
4. 已授权客户数。
5. 今日发送数。
6. 已回复数。
7. 已读未回复数。
8. 发送失败数。
9. 账号异常数。

### 6.2 TG 账号管理

功能：

1. 上传 session ZIP。
2. 查看账号列表。
3. 查看账号状态。
4. 设置账号每日发送上限。
5. 启用或暂停账号。
6. 查看账号最近错误。
7. 查看账号发送量、回复量、失败量。
8. 按账号分组筛选。
9. 批量移动账号到分组。
10. 批量分配客服。
11. 批量上线、下线、归档账号。
12. 绑定、解绑或更换账号使用的网络代理。

建议筛选项：

| 筛选项 | 说明 |
| --- | --- |
| 国家 | 账号手机号所属国家 |
| 账号分组 | 当前账号所属分组 |
| 客服账号 | 已绑定的客服人员 |
| 在线状态 | 在线、离线、未知 |
| 账号状态 | 正常、暂停、受限、异常 |
| 手机号 | 精确或模糊搜索 |
| 设备数量 | 当前 session/设备数量 |
| 代理状态 | 未配置、正常、异常、检测中 |

### 6.2.1 账号分组管理

功能：

1. 新建账号分组。
2. 编辑账号分组名称、每日上限、备注。
3. 查看分组下账号数量、可用账号数、今日发送数、失败数。
4. 设置分组是否启用。
5. 设置分组可见客服。
6. 查看分组任务列表。

### 6.2.2 网络代理管理

功能：

1. 新增代理。
2. 批量导入代理。
3. 编辑代理地址、端口、协议、认证信息和备注。
4. 检测代理可用性。
5. 查看代理延迟、最近失败原因、绑定账号数。
6. 将代理绑定到指定 TG 账号。
7. 批量为账号分配代理。
8. 禁用异常代理。

支持协议建议：

| 协议 | 说明 |
| --- | --- |
| socks5 | 优先支持，Telegram 客户端常用 |
| http | 可选支持 |
| https | 可选支持 |

代理列表字段建议：

| 字段 | 说明 |
| --- | --- |
| 名称 | 便于识别 |
| 协议 | socks5/http/https |
| 主机 | 代理 Host |
| 端口 | 代理端口 |
| 用户名 | 可选 |
| 密码 | 加密存储，不明文展示 |
| 国家/地区 | 出口区域 |
| 状态 | 正常、异常、禁用、检测中 |
| 延迟 | 最近一次检测延迟 |
| 绑定账号数 | 当前使用该代理的账号数量 |
| 最近错误 | 最近连接失败原因 |

### 6.3 客户管理

功能：

1. 批量导入客户。
2. 客户列表筛选。
3. 按状态筛选：
   - 未触达
   - 已分配
   - 已发送
   - 已读未回复
   - 已回复
   - 发送失败
4. 查看客户来源和标签。
5. 查看客户分配账号。
6. 查看最近发送内容和回复内容。

### 6.3.1 好友列表

好友列表用于管理从 TG 账号同步回来的联系人或已有聊天对象。

功能：

1. 按账号分组筛选好友。
2. 按账号昵称、手机号、状态、日期筛选。
3. 导出好友。
4. 查看好友所属 TG 账号。
5. 查看好友最近互动状态。
6. 将好友加入群发任务候选范围。

好友状态建议：

| 状态 | 说明 |
| --- | --- |
| new | 新同步 |
| contacted | 已联系 |
| read | 已读 |
| replied | 已回复 |
| blocked | 已拉黑或不可达 |
| opted_out | 不再联系 |

### 6.4 分配管理

功能：

1. 选择客户范围。
2. 选择参与分配的 TG 账号。
3. 设置每账号分配上限。
4. 执行分配。
5. 查看分配结果。

### 6.5 模板管理

功能：

1. 创建模板。
2. 编辑模板。
3. 预览变量替换效果。
4. 设置模板启用状态。
5. 查看模板历史使用次数。

### 6.6 发送任务

功能：

1. 创建发送任务。
2. 选择模板。
3. 选择客户范围。
4. 检查风险和额度。
5. 创建发送队列。
6. 暂停、继续、取消任务。
7. 查看任务详情和失败原因。
8. 设置每条消息发送间隔。
9. 设置随机间隔和失败间隔。
10. 设置参与任务的账号分组。
11. 设置任务并行账号数。
12. 查看队列进度、预计完成时间和当前执行账号。

新增任务弹窗建议字段：

| 字段 | 说明 |
| --- | --- |
| 任务名称 | 默认生成，也允许人工修改 |
| 操作对象 | 用户数据、好友数据、导入数据 |
| 用户数据分组 | 客户数据分组 |
| 客服分组 | 可用账号分组或客服组 |
| 消息类型 | 文本、图片、文件，首期先文本 |
| 资料分组 | 可选，用于资料或素材关联 |
| 来源 | 通过搜索、导入、已有好友 |
| 添加联系人 | 是否先添加联系人再发送 |
| 成功间隔 | 成功发送后等待时间 |
| 失败间隔 | 失败后等待时间 |
| 随机间隔 | 每条消息附加随机等待 |
| 线程数 | 同时执行的账号数量，不是单账号并发 |
| 分批间隔 | 每处理一批后等待时间 |

### 6.7 回复管理

功能：

1. 展示已回复客户。
2. 按账号、任务、时间筛选。
3. 查看最近回复内容。
4. 标记处理状态。
5. 跳转到客户详情。

### 6.8 客服中心

客服中心用于管理客服人员、客服权限和每日统计。

功能：

1. 新增客服。
2. 编辑客服资料。
3. 设置客服可用账号分组。
4. 设置客服可见聊天分类。
5. 设置客服操作权限。
6. 查看今日接待数、今日读取数、今日发送数、读取率、回复率。
7. 打开客服工作台页面。

客服权限建议拆成三层：

| 权限层 | 说明 |
| --- | --- |
| 数据范围 | 可见哪些账号分组、客户分组、好友分组 |
| 操作权限 | 能否发送、删除好友、修改资料、清理聊天记录 |
| 聊天权限 | 能否看到未读、已读、未回复、已互动等会话 |

## 7. 数据结构规划

### 7.1 TG 账号 Account

| 字段 | 说明 |
| --- | --- |
| id | 系统账号 ID |
| tgUserId | Telegram 用户 ID 或导入目录名 |
| phone | 账号绑定手机号，可选 |
| sessionPath | session 文件保存路径 |
| proxyId | 绑定的网络代理 ID，可为空 |
| status | 账号状态 |
| enabled | 是否启用 |
| dailyLimit | 每日发送上限 |
| sentToday | 今日已发送 |
| totalSent | 累计发送 |
| totalReplies | 累计回复 |
| lastLoginAt | 最近登录时间 |
| lastError | 最近错误 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.1.1 网络代理 ProxyEndpoint

| 字段 | 说明 |
| --- | --- |
| id | 代理 ID |
| name | 代理名称 |
| protocol | 协议：socks5/http/https |
| host | 主机 |
| port | 端口 |
| username | 用户名，可选 |
| passwordEncrypted | 加密后的密码 |
| country | 国家/地区 |
| status | 正常、异常、禁用、检测中 |
| latencyMs | 最近检测延迟 |
| lastCheckedAt | 最近检测时间 |
| lastError | 最近错误 |
| maxAccounts | 最大绑定账号数，可选 |
| remark | 备注 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.1.2 账号代理变更日志 AccountProxyLog

| 字段 | 说明 |
| --- | --- |
| id | 日志 ID |
| accountId | TG 账号 ID |
| oldProxyId | 原代理 ID |
| newProxyId | 新代理 ID |
| action | bind、unbind、switch、disable |
| reason | 操作原因 |
| createdBy | 操作人 |
| createdAt | 创建时间 |

### 7.1.3 账号分组 AccountGroup

| 字段 | 说明 |
| --- | --- |
| id | 分组 ID |
| name | 分组名称 |
| code | 分组编码 |
| enabled | 是否启用 |
| dailyLimit | 分组每日发送上限 |
| sentToday | 分组今日已发送 |
| remark | 备注 |
| createdBy | 创建人 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.1.4 账号分组关系 AccountGroupMember

| 字段 | 说明 |
| --- | --- |
| id | 关系 ID |
| accountId | TG 账号 ID |
| groupId | 账号分组 ID |
| isPrimary | 是否主分组 |
| createdAt | 创建时间 |

### 7.2 客户 Customer

| 字段 | 说明 |
| --- | --- |
| id | 客户 ID |
| phone | 手机号 |
| name | 姓名 |
| tags | 标签 |
| source | 来源 |
| consent | 是否授权联系 |
| assignedAccountId | 分配的 TG 账号 |
| status | 客户触达状态 |
| lastMessageAt | 最近触达时间 |
| lastReadAt | 最近已读时间 |
| lastReplyAt | 最近回复时间 |
| lastReplyText | 最近回复内容 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.2.1 好友 Friend

| 字段 | 说明 |
| --- | --- |
| id | 好友 ID |
| accountId | 所属 TG 账号 |
| accountGroupId | 所属账号分组，冗余字段便于筛选 |
| tgUserId | Telegram 用户 ID |
| username | Telegram username |
| phone | 手机号 |
| nickname | 昵称 |
| avatarUrl | 头像 |
| status | 好友状态 |
| lastMessageAt | 最近消息时间 |
| lastReadAt | 最近已读时间 |
| lastReplyAt | 最近回复时间 |
| optedOut | 是否不再联系 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.3 消息模板 MessageTemplate

| 字段 | 说明 |
| --- | --- |
| id | 模板 ID |
| name | 模板名称 |
| body | 模板内容 |
| enabled | 是否启用 |
| createdBy | 创建人 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.4 发送任务 Campaign

| 字段 | 说明 |
| --- | --- |
| id | 任务 ID |
| name | 任务名称 |
| templateId | 模板 ID |
| status | 任务状态 |
| targetCount | 目标客户数 |
| queuedCount | 队列数 |
| sentCount | 发送成功数 |
| readCount | 已读数 |
| replyCount | 回复数 |
| failedCount | 失败数 |
| createdBy | 创建人 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

扩展字段：

| 字段 | 说明 |
| --- | --- |
| targetType | 目标类型：客户、好友、导入目标 |
| accountGroupIds | 参与发送的账号分组 |
| customerGroupId | 客户数据分组，可选 |
| friendFilter | 好友筛选条件快照 |
| sendSettings | 发送间隔与并发配置快照 |
| startedAt | 开始时间 |
| pausedAt | 暂停时间 |
| completedAt | 完成时间 |

### 7.5 消息记录 MessageRecord

| 字段 | 说明 |
| --- | --- |
| id | 消息记录 ID |
| campaignId | 任务 ID |
| accountId | 发送账号 ID |
| customerId | 客户 ID |
| phone | 客户手机号 |
| bodySnapshot | 实际发送内容快照 |
| status | 消息状态 |
| sentAt | 发送时间 |
| readAt | 已读时间 |
| repliedAt | 回复时间 |
| replyText | 回复内容 |
| errorCode | 错误码 |
| errorMessage | 错误说明 |
| nextRunAt | 下一次可执行时间 |
| attemptCount | 已尝试次数 |
| lockedBy | 当前处理 worker |
| lockedAt | 锁定时间 |

### 7.6 客服人员 SupportAgent

| 字段 | 说明 |
| --- | --- |
| id | 客服 ID |
| username | 登录用户名 |
| nickname | 昵称 |
| status | 启用、禁用 |
| onlineStatus | 在线、离线 |
| lastLoginAt | 最近登录时间 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 7.7 客服账号分组权限 SupportAgentGroupPermission

| 字段 | 说明 |
| --- | --- |
| id | 权限 ID |
| agentId | 客服 ID |
| accountGroupId | 可用账号分组 ID |
| canViewFriends | 是否可见好友 |
| canViewChats | 是否可见聊天 |
| canSendMessage | 是否可发送 |
| canBroadcast | 是否可创建群发 |
| canEditProfile | 是否可修改账号资料 |
| canDeleteFriend | 是否可删除好友 |
| canClearChat | 是否可清理聊天记录 |
| chatScope | 可见聊天分类配置 |
| createdAt | 创建时间 |

## 8. Telegram 接入设计

### 8.1 Session 导入

ZIP 包结构：

```text
sessions.zip
  123456789/
    account.session
  987654321/
    account.session
```

导入规则：

1. 只读取 `.session` 文件。
2. 一级目录作为账号标识。
3. 同一 `userid` 重复导入时更新 session 文件。
4. 不在页面展示 session 内容。
5. session 文件必须保存在服务端私有目录。

### 8.2 发送适配层

建议将 Telegram 能力封装为独立 adapter：

```text
TelegramAdapter
  validateSession(account)
  sendMessage(account, customer, message)
  listenIncoming(account)
  getReadStatus(account, message)
  checkProxy(proxy)
```

业务层不直接依赖具体 Telegram 库，避免后续替换成本过高。

Telegram adapter 初始化账号连接时，需要读取账号绑定的代理配置：

```text
Account.proxyId
  -> ProxyEndpoint
  -> Telethon connection proxy config
```

同一个账号的以下操作必须使用同一份连接配置：

1. session 校验。
2. 好友同步。
3. 单聊发送。
4. 群发任务发送。
5. 回复监听。
6. 已读状态同步。

### 8.3 Worker 执行模型

建议采用后台 worker：

1. 从消息队列读取待发送记录。
2. 检查账号状态。
3. 检查账号每日额度。
4. 检查任务是否暂停。
5. 发送单条消息。
6. 更新消息状态。
7. 记录失败原因。
8. 按账号维度进行频控。
9. 使用账号绑定的代理连接 Telegram。
10. 如果代理不可用，暂停该账号队列并记录错误。

## 9. 风控与合规要求

系统必须内置以下限制：

1. 未授权客户不得进入发送队列。
2. 支持客户退订或拉黑标记。
3. 每个账号设置每日发送上限。
4. 每个任务设置发送速率上限。
5. 账号出现异常时自动暂停。
6. 连续失败达到阈值时自动熔断。
7. 所有导入、分配、发送、暂停操作写入审计日志。
8. 后台明确展示客户来源和授权状态。
9. 不提供规避 Telegram 风控、绕过封禁或隐藏真实身份的功能。
10. 网络代理只作为连接配置管理，不提供绕过平台限制、规避封禁或隐藏异常行为的功能。
11. 代理切换必须记录日志，并建议限制频率，避免同一账号频繁更换出口网络。

## 10. 技术架构建议

### 10.1 首期架构

```text
Web Admin
  |
Backend API
  |
MySQL 8
  |
Redis Queue
  |
Telegram Worker
  |
Telegram Adapter
```

### 10.2 技术选型建议

| 层级 | 建议 |
| --- | --- |
| 前端 | React / Vue 均可 |
| 后端 | Python FastAPI |
| 数据库 | MySQL 8 |
| 队列 | Redis + Celery / RQ |
| 文件存储 | 本地私有目录或对象存储 |
| 实时通知 | WebSocket / Server-Sent Events |
| 部署 | Docker Compose 起步 |

如果项目需要快速验证，可以先用 FastAPI + MySQL 8 + Redis + Telethon 做 MVP。TG session、发送、监听和账号状态同步建议统一放在 Python worker 中，前端只通过 API 操作业务对象。

### 10.2.1 语言和数据库选择结论

推荐主栈：

```text
后端 API：Python + FastAPI
Telegram Worker：Python + Telethon
数据库：MySQL 8
队列/缓存/锁：Redis
前端：Vue 3 或 React
```

选择 Python 的原因：

1. Telegram session、发送、监听和账号状态同步更适合用 Python 生态实现。
2. Telethon 对 `.session` 文件、多账号连接、事件监听和错误类型处理更成熟。
3. API 服务和 worker 可以共用同一套模型、权限和业务校验逻辑。
4. 后续做定时任务、发送调度、失败重试会更直接。

选择 MySQL 8 的原因：

1. 本系统核心数据是账号、分组、客服、客户、好友、任务、消息记录，典型关系型结构。
2. MySQL 8 对索引、事务、行锁、JSON 字段、分页查询都够用。
3. 国内服务器、面板、运维工具和团队经验通常对 MySQL 更友好。
4. 群发队列不建议直接依赖数据库轮询，使用 Redis/Celery 后，MySQL 压力主要来自业务查询和状态落库。

什么时候考虑 PostgreSQL：

1. 后续需要复杂 JSONB 查询、全文检索、复杂统计分析。
2. 团队已经熟悉 PostgreSQL 运维。
3. 希望大量使用数据库原生能力做报表、分区和分析。

首期不建议使用 MongoDB 作为主库。这个项目权限关系和状态流转很多，关系型数据库更清晰。

### 10.3 后端模块划分

后端建议按业务域拆模块，而不是按页面拆文件。

```text
backend/
  app/
    api/                  # HTTP API 路由
    core/                 # 配置、鉴权、日志、异常
    modules/
      auth/               # 登录、角色、权限
      accounts/           # TG 账号、session、账号分组
      proxies/            # 网络代理、代理检测、账号代理绑定
      agents/             # 客服人员、客服分组权限
      customers/          # 客户数据、客户分组
      friends/            # TG 好友同步与查询
      templates/          # 消息模板
      campaigns/          # 群发任务、队列生成
      messages/           # 消息记录、状态流转
      statistics/         # 仪表盘、任务统计
      audit/              # 操作日志
      telegram/           # Telegram adapter
    workers/
      send_worker.py      # 发送队列 worker
      listen_worker.py    # 回复监听 worker
      account_worker.py   # session 校验和账号状态同步
```

### 10.4 核心服务职责

| 服务 | 职责 |
| --- | --- |
| AccountService | session 导入、账号状态、账号分组、账号额度 |
| ProxyService | 代理导入、健康检测、账号绑定、代理状态 |
| PermissionService | 判断客服是否可见账号分组、客户、好友和任务 |
| CustomerService | 客户导入、去重、授权状态、客户分组 |
| FriendService | 同步好友、好友筛选、好友状态 |
| CampaignService | 创建群发任务、校验权限、生成队列 |
| DispatchService | 按账号、分组、任务规则选择下一条待发送记录 |
| MessageService | 消息状态流转、失败记录、回复绑定 |
| TelegramService | 调用 Telethon/Pyrogram 完成发送、监听和 session 校验 |
| StatisticsService | 账号、分组、客服、任务维度统计 |
| AuditService | 写入关键操作日志 |

### 10.5 API 边界规划

账号与分组：

```text
POST   /api/accounts/import-zip
GET    /api/accounts
PATCH  /api/accounts/{id}
POST   /api/account-groups
GET    /api/account-groups
PATCH  /api/account-groups/{id}
POST   /api/account-groups/{id}/members
DELETE /api/account-groups/{id}/members/{accountId}
POST   /api/proxies
GET    /api/proxies
PATCH  /api/proxies/{id}
POST   /api/proxies/{id}/check
POST   /api/accounts/{id}/proxy
DELETE /api/accounts/{id}/proxy
```

客服与权限：

```text
POST   /api/support-agents
GET    /api/support-agents
PATCH  /api/support-agents/{id}
PUT    /api/support-agents/{id}/account-group-permissions
GET    /api/support-agents/{id}/account-group-permissions
```

客户与好友：

```text
POST   /api/customers/import
GET    /api/customers
GET    /api/friends
POST   /api/friends/sync
```

模板与群发任务：

```text
POST   /api/message-templates
GET    /api/message-templates
POST   /api/campaigns
GET    /api/campaigns
GET    /api/campaigns/{id}
POST   /api/campaigns/{id}/start
POST   /api/campaigns/{id}/pause
POST   /api/campaigns/{id}/resume
POST   /api/campaigns/{id}/cancel
GET    /api/campaigns/{id}/messages
```

统计与日志：

```text
GET    /api/statistics/dashboard
GET    /api/statistics/accounts
GET    /api/statistics/account-groups
GET    /api/statistics/support-agents
GET    /api/audit-logs
```

### 10.6 权限过滤原则

所有列表查询和操作接口都必须先做数据范围过滤。

```text
当前用户
  -> 查询其可用 accountGroupIds
  -> 所有 account / friend / customer / campaign 查询都追加 accountGroupId IN (...)
  -> 所有发送、修改、删除操作再次校验 canSendMessage / canBroadcast / canEditProfile 等操作权限
```

不能只在前端隐藏按钮，后端必须强制校验。

### 10.7 群发调度算法

发送 worker 每次只处理到达 `nextRunAt` 的消息记录。

```text
1. 拉取状态为 queued/retry 且 nextRunAt <= now 的消息记录
2. 使用数据库行锁或 Redis 锁锁定记录
3. 检查 Campaign 状态是否 running
4. 检查 Account 状态是否 active
5. 检查 Account 绑定代理是否可用
6. 检查 AccountGroup 是否启用且未超过每日上限
7. 检查 Account 是否超过每日上限
8. 检查当前是否在静默时段
9. 调用 TelegramAdapter.sendMessage
10. 成功则更新 message.status=sent，计算账号下一条 nextRunAt
11. 失败则记录 errorCode/errorMessage，按失败间隔计算 retry nextRunAt
12. 如果连续失败达到阈值，暂停账号或任务
```

为了保证同一个账号不会同时发送多条消息，建议对 `accountId` 增加发送锁：

```text
send_lock:{accountId}
```

锁的 TTL 可以设置为 `successIntervalSeconds + randomMaxSeconds + 30`。

### 10.8 状态流转

消息状态：

```text
queued -> sending -> sent -> read -> replied
queued -> sending -> failed -> retry
retry  -> sending -> sent
retry  -> failed_permanent
queued -> cancelled
```

账号状态：

```text
imported -> validating -> active
active -> paused
active -> limited
active -> error
limited -> active
error -> validating
```

任务状态：

```text
draft -> queued -> running -> completed
running -> paused -> running
running -> throttled -> running
running -> partially_failed
running -> cancelled
```

### 10.9 定时任务

| 任务 | 周期 | 说明 |
| --- | --- | --- |
| session 校验 | 5-30 分钟 | 校验账号是否可登录 |
| 代理健康检测 | 5-30 分钟 | 检测代理连通性、延迟和失败原因 |
| 账号统计刷新 | 1-5 分钟 | 汇总发送量、失败量、回复量 |
| 每日额度重置 | 每日 00:00 | 重置账号和分组 `sentToday` |
| 失败任务扫描 | 1-5 分钟 | 标记长时间无进展任务 |
| 回复监听保活 | 常驻 | 监听消息事件并自动重连 |
| 审计日志归档 | 每日 | 大表归档或分区 |

### 10.10 部署架构

首期推荐采用“数据库和 Redis 安装在宿主机，业务程序使用 Docker 运行”的部署方式。

```text
服务器宿主机
  MySQL 8
  Redis 7
  /opt/tg-support-hub/data/
    sessions/
    uploads/
    logs/

Docker / Docker Compose
  backend-api      Python FastAPI
  worker-send      Celery 发送任务 worker
  worker-listen    Telegram 回复监听 worker
  worker-account   session 校验、账号状态同步、代理检测
  frontend-nginx   Vue 静态页面和反向代理
```

这种方式的优点：

1. MySQL 和 Redis 由服务器直接管理，方便使用命令行、面板、Navicat 和监控工具维护。
2. 业务程序仍然容器化，发版和回滚更简单。
3. session、上传文件和日志落在宿主机固定目录，容器重建不会丢数据。

需要注意：

1. MySQL 不开放公网端口，只允许本机或内网访问。
2. Redis 不开放公网端口，必须设置密码，建议监听 `127.0.0.1` 或内网 IP。
3. backend 和 worker 使用同一套 `.env` 配置连接 MySQL、Redis 和文件目录。
4. Docker 容器需要能访问宿主机的 MySQL 和 Redis。
5. session 文件目录必须挂载给 backend、worker-send、worker-listen 和 worker-account。

推荐目录结构：

```text
/opt/tg-support-hub/
  docker-compose.yml
  .env
  data/
    sessions/
    uploads/
    logs/
  backup/
    mysql/
    sessions/
    uploads/
```

Docker 连接宿主机服务时，建议在 `docker-compose.yml` 中配置：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

然后 `.env` 中使用：

```env
MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
REDIS_HOST=host.docker.internal
REDIS_PORT=6379
```

如果服务器环境不支持 `host-gateway`，可以使用 Docker 默认网桥网关，例如：

```env
MYSQL_HOST=172.17.0.1
REDIS_HOST=172.17.0.1
```

具体地址需要在服务器上确认。

### 10.11 部署环境变量

建议统一使用 `.env` 管理配置，避免写死在代码里。

```env
APP_ENV=production
APP_SECRET=replace-with-random-secret

MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
MYSQL_DATABASE=tg_support_hub
MYSQL_USER=tg_support
MYSQL_PASSWORD=replace-with-strong-password

REDIS_HOST=host.docker.internal
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-strong-password

TELEGRAM_API_ID=replace-with-api-id
TELEGRAM_API_HASH=replace-with-api-hash

SESSION_DIR=/app/data/sessions
UPLOAD_DIR=/app/data/uploads
LOG_DIR=/app/data/logs
```

敏感配置要求：

1. `.env` 不提交到 Git。
2. 数据库密码、Redis 密码、JWT/应用密钥必须使用强随机值。
3. Telegram API Hash、session 文件、代理密码都应视为敏感数据。

### 10.12 持久化与备份

必须持久化的数据：

| 数据 | 位置 | 备份建议 |
| --- | --- | --- |
| MySQL 数据 | 宿主机 MySQL 数据目录 | 每日备份 |
| Redis 数据 | 宿主机 Redis 数据目录 | 可选，队列任务重要时开启 |
| TG session | `/opt/tg-support-hub/data/sessions` | 每日备份，加密保存 |
| 上传文件 | `/opt/tg-support-hub/data/uploads` | 每日备份 |
| 运行日志 | `/opt/tg-support-hub/data/logs` | 保留 7-30 天 |
| `.env` | `/opt/tg-support-hub/.env` | 单独安全保存 |

备份策略：

1. MySQL 每日 `mysqldump`，至少保留 7 天。
2. session 文件每日打包备份，建议加密。
3. 上传文件按天增量备份。
4. 恢复演练至少在上线前做一次，确认数据库和 session 能恢复。

### 10.13 上线步骤

1. 准备 Ubuntu 22.04 或 24.04 服务器。
2. 安装 MySQL 8，并创建数据库和业务用户。
3. 安装 Redis 7，设置密码并限制监听地址。
4. 安装 Docker 和 Docker Compose。
5. 创建 `/opt/tg-support-hub/` 目录。
6. 配置 `.env`。
7. 创建 `data/sessions`、`data/uploads`、`data/logs` 目录。
8. 启动 backend，执行数据库迁移。
9. 启动 worker-send、worker-listen、worker-account。
10. 启动 frontend-nginx。
11. 配置域名和 HTTPS。
12. 验证登录、session 导入、账号校验、代理检测、任务创建和 worker 执行。

## 11. 权限设计

首期可设计三类权限：

| 权限 | 管理员 | 主管 | 客服 |
| --- | --- | --- | --- |
| 导入 TG 账号 | 是 | 否 | 否 |
| 管理账号状态 | 是 | 部分 | 否 |
| 管理账号分组 | 是 | 是 | 否 |
| 分配客服可用分组 | 是 | 是 | 否 |
| 导入客户 | 是 | 是 | 否 |
| 创建群发任务 | 是 | 是 | 按授权 |
| 设置发送间隔 | 是 | 是 | 按授权 |
| 暂停/继续任务 | 是 | 是 | 按授权 |
| 查看全局统计 | 是 | 是 | 否 |
| 查看分组统计 | 是 | 是 | 按授权 |
| 查看分配客户 | 是 | 是 | 按授权 |
| 处理客户回复 | 是 | 是 | 是 |

### 11.1 账号分组权限模型

客服人员是否能使用某个 TG 账号，不直接绑定账号，而是绑定账号分组。

```text
SupportAgent
  -> SupportAgentGroupPermission
  -> AccountGroup
  -> Account
```

这样做的好处：

1. 新增 TG 账号时，只需要放入分组，客服自动获得权限。
2. 调整客服负责范围时，只需要修改分组权限。
3. 群发任务可以按分组选择账号池。
4. 统计可以按分组聚合。

### 11.2 操作权限明细

| 权限项 | 说明 |
| --- | --- |
| canViewAccounts | 可查看账号列表 |
| canUseAccounts | 可使用账号进行聊天 |
| canViewFriends | 可查看好友列表 |
| canViewChats | 可查看聊天记录 |
| canSendMessage | 可手动发送消息 |
| canBroadcast | 可创建群发任务 |
| canPauseCampaign | 可暂停群发任务 |
| canEditAccountProfile | 可修改账号资料 |
| canDeleteFriend | 可删除好友 |
| canClearChat | 可清理聊天记录 |
| canExportData | 可导出数据 |

### 11.3 聊天范围权限

聊天权限不只是“能不能看”，还需要区分会话分类。

| 范围 | 说明 |
| --- | --- |
| all | 全部聊天 |
| unread | 未读聊天 |
| read | 已读聊天 |
| unreplied | 未回复聊天 |
| newMessage | 有新消息 |
| interacted | 已互动 |
| proactiveOnly | 只显示主动发送过消息的好友 |

## 12. MVP 交付计划

### 阶段一：产品原型与本地数据闭环

目标：验证后台流程。

交付：

1. Web 管理后台。
2. session ZIP 导入。
3. 账号分组管理。
4. 客服人员管理。
5. 客服可用账号分组授权。
6. 客户导入。
7. 客户分配。
8. 模板管理。
9. 群发任务队列。
10. 发送间隔配置。
11. 模拟发送结果。
12. 状态看板。

### 阶段二：Telegram session 校验与真实发送

目标：打通真实 Telegram 能力。

交付：

1. Telegram API 配置。
2. session 有效性校验。
3. 单条消息发送。
4. 队列 worker。
5. 发送失败原因记录。
6. 账号频控。
7. 分组额度控制。
8. 任务暂停、继续、取消。

### 阶段三：回复监听与客服处理

目标：形成客服闭环。

交付：

1. 回复监听。
2. 客户状态自动更新。
3. 回复列表。
4. 客户详情。
5. 客服处理状态。
6. 好友同步与好友列表。
7. 客服权限下的聊天可见范围控制。

### 阶段四：权限、审计与部署

目标：上线可运营。

交付：

1. 登录和权限。
2. 操作审计。
3. 数据导出。
4. Docker 部署。
5. 备份策略。
6. 监控告警。
7. 审计日志归档。

## 13. 验收标准

MVP 验收建议：

1. 可以成功上传包含 `userid/*.session` 的 ZIP 包。
2. 系统能展示导入账号列表。
3. 每个账号可以归属到账号分组。
4. 可以给客服人员配置可用账号分组。
5. 客服只能看到授权分组下的账号、好友、客户和任务。
6. 可以导入客户手机号并完成去重。
7. 未授权客户不会进入发送队列。
8. 可以将客户平均分配给多个账号。
9. 可以创建消息模板。
10. 可以创建群发任务。
11. 可以设置每条消息的成功间隔、失败间隔和随机间隔。
12. 群发任务可以暂停、继续、取消。
13. 可以看到客户状态分类统计。
14. 可以看到账号维度发送量、回复量、失败量。
15. 可以看到账号分组维度统计。
16. 所有关键操作有记录可追溯。

## 14. 关键风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| Telegram session 失效 | 账号无法发送 | 增加 session 校验和异常提醒 |
| 账号被限制 | 发送中断 | 设置频控、日限额、失败熔断 |
| 客户数据未授权 | 合规风险 | 导入时必须记录授权状态 |
| 批量发送失败 | 任务效果不稳定 | 引入队列、重试、失败原因统计 |
| 回复无法匹配客户 | 客服跟进困难 | 保存 TG 用户标识和手机号映射 |
| 数据泄露 | 高风险 | 加密存储 session，限制后台权限 |
| 客服越权使用账号 | 数据和账号风险 | 后端按账号分组强制鉴权 |
| 群发速度过快 | 账号受限或触达质量下降 | 强制设置发送间隔、随机间隔、日限额 |
| 单账号并发发送 | 消息乱序和账号异常 | 单账号发送锁，默认单账号并发为 1 |
| 任务重复发送 | 客户体验差和合规风险 | 以客户/好友/任务维度做幂等约束 |
| 大任务拖垮系统 | 队列积压 | 分批生成队列、分页执行、任务限额 |
| 代理不可用 | 账号无法登录或发送失败 | 代理健康检测，异常时暂停账号 |
| 频繁切换代理 | 登录环境变化导致账号异常 | 默认固定绑定代理，切换需审计 |
| 代理密码泄露 | 安全风险 | 加密存储，不在页面明文展示 |

## 15. 后续待确认问题

1. TG 账号 session 是来自 Telethon、Pyrogram，还是其他客户端库？
2. 客户手机号是否都能直接在 Telegram 中找到对应用户？
3. 首期是否需要真实发送，还是先做模拟流程？
4. 是否需要客服人员登录和权限隔离？
5. 是否需要支持客户退订、黑名单或不再联系标记？
6. 每个账号每日期望发送上限是多少？
7. 是否需要导入 Excel，还是 CSV/文本即可？
8. 是否需要将回复同步给外部 CRM？
9. 账号分组是一个账号只属于一个分组，还是允许多分组？
10. 客服是否允许手动切换发送账号，还是系统自动选择账号？
11. 群发对象首期优先做客户数据，还是已有好友列表？
12. 发送间隔是按账号生效，还是按整个任务生效？
13. 是否需要群发任务审核后才能启动？
14. 是否需要限制同一个客户在 N 天内只能收到一次群发？
15. 代理类型优先支持 socks5，还是也需要 http/https？
16. 每个账号是否固定绑定一个代理，还是允许从代理池自动分配？
17. 代理是否需要按国家/地区与账号手机号归属地匹配？
18. 一个代理最多允许绑定多少个 TG 账号？
19. 代理检测失败后，是自动暂停账号，还是允许临时改走服务器默认网络？
