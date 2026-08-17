import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("密码").fill("123456");
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("heading", { name: "患者预约交付工作台" })).toBeVisible();
  await expect(page.getByRole("main", { name: "患者会话" })).toBeVisible();
}

async function signInAs(page: import("@playwright/test").Page, role: "operator" | "admin") {
  await page.goto("/");
  await page.getByLabel("演示身份").selectOption(role);
  await page.getByLabel("密码").fill("123456");
  await page.getByRole("button", { name: "进入工作台" }).click();
}

test("右上角账号菜单重新认证后可切换到人工客服", async ({ page }) => {
  await signIn(page);

  const accountTrigger = page.getByRole("button", { name: /演示患者.*患者/ });
  await accountTrigger.click();
  await page.getByRole("button", { name: "切换演示身份" }).click();
  const dialog = page.getByRole("dialog", { name: "切换演示身份" });
  await expect(dialog).toBeVisible();
  await page.getByLabel("切换到演示身份").selectOption("operator");
  await page.getByLabel("密码").fill("123456");
  await page.getByRole("button", { name: "确认切换" }).click();

  await expect(page.getByRole("heading", { name: "人工客服工作台" })).toBeVisible();
  await expect(page.getByRole("button", { name: /演示客服.*人工客服/ })).toBeVisible();
});

test("完整的未来预约示例直接查询，不追问创建预约字段", async ({ page }) => {
  await signIn(page);

  await page.getByRole("button", { name: "查询我未来的预约" }).click();

  await expect(page.locator(".message--patient p")).toHaveText("查询我未来的预约");
  await expect(page.getByText("暂无未来预约。")).toBeVisible();
  await expect(page.getByText("还需要确认：服务项目、日期。")).toHaveCount(0);
});

test("患者可以通过真实 API 完成预约选择、确认与运行状态查看", async ({ page }, testInfo) => {
  await signIn(page);

  await page.getByLabel("输入预约需求").fill("我想预约2026年8月15日下午洗牙");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "请选择预约时段" })).toBeVisible();

  await page.locator(".option-row").first().click();
  await expect(page.getByRole("heading", { name: "请确认以下预约信息" })).toBeVisible();

  await page.getByRole("button", { name: "确认预约" }).click();
  await expect(page.getByText("预约已成功")).toBeVisible();
  await expect(page.getByLabel("患者会话")).not.toContainText("当前执行上下文");
  await page.getByLabel("输入预约需求").fill("查询我未来的预约");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "您的预约详情" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "您的预约详情" })).toBeInViewport();
  const appointmentDetails = page.getByRole("region", { name: "您的预约详情" });
  await expect(appointmentDetails.getByText("洗牙", { exact: true })).toBeVisible();
  await expect(appointmentDetails.getByText("张医生", { exact: true })).toBeVisible();
  await expect(appointmentDetails).not.toContainText("SV-CLEANING");
  await expect(appointmentDetails).not.toContainText("预约已成功");
  const screenshot = testInfo.outputPath("patient-workspace.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("patient-workspace", { path: screenshot, contentType: "image/png" });
});

test("患者可通过服务项目、可约日期和时段完成引导式预约", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想创建预约");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByRole("heading", { name: "请选择服务项目" })).toBeVisible();
  await page.getByRole("button", { name: /洗牙.*预计 60 分钟.*选择/ }).click();
  await expect(page.getByRole("heading", { name: "请选择可约日期" })).toBeVisible();
  await page.getByRole("button", { name: /8月15日.*2 个可约时段.*查看当天时段/ }).click();
  await expect(page.getByRole("heading", { name: "请选择预约时段" })).toBeVisible();
  await expect(page.locator(".option-row")).toHaveCount(2);
});

test("所选服务项目未来7天没有可约日期时，退回服务项目选择而不是卡死", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想创建预约");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByRole("heading", { name: "请选择服务项目" })).toBeVisible();
  await page.getByRole("button", { name: /口腔检查.*选择/ }).click();

  await expect(page.getByText("口腔检查在未来 7 天暂时没有可约时段，请换一个服务项目。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "请选择服务项目" })).toBeVisible();
  await expect(page.getByRole("button", { name: /洗牙.*预计 60 分钟.*选择/ })).toBeEnabled();
  const firstStep = page.locator(".booking-progress li").first();
  await expect(firstStep).not.toHaveClass(/booking-progress__step--done/);

  // 连续两次选同一个零号源服务项目，两次回复文案完全相同；即便如此，第二次点击也必须
  // 产生真实反馈（新的一条 Agent 气泡），不能因为文案去重而让页面看起来“点了没反应”。
  await page.getByRole("button", { name: /口腔检查.*选择/ }).click();
  await expect(page.getByText("口腔检查在未来 7 天暂时没有可约时段，请换一个服务项目。")).toHaveCount(2);
  await expect(page.getByRole("heading", { name: "请选择服务项目" })).toBeVisible();
});

test("引导式服务与日期候选在窄屏不产生水平页面溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想创建预约");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "请选择服务项目" })).toBeVisible();
  expect(await page.locator("html").evaluate((element) => element.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: /洗牙.*预计 60 分钟.*选择/ }).click();
  await expect(page.getByRole("heading", { name: "请选择可约日期" })).toBeVisible();
  expect(await page.locator("html").evaluate((element) => element.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("人工接管暂停自动推进但允许患者继续沟通", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想预约2026年8月16日上午洗牙");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "请选择预约时段" })).toBeVisible();

  await page.getByRole("button", { name: "请求人工客服" }).click();
  await expect(page.getByText("当前已由人工客服接管")).toBeVisible();
  const composer = page.getByLabel("输入预约需求");
  await expect(composer).toBeEnabled();
  await expect(composer).toHaveAttribute("placeholder", "补充信息给人工客服");
  await composer.fill("我还想补充：周末下午更方便");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("我还想补充：周末下午更方便")).toBeVisible();
  await expect(page.getByText("人工接管期间，Agent 自动执行与业务推进已暂停")).toBeVisible();
});

test("精确条件无号源后，快捷回复只填入输入框并由患者主动发送", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想预约2026年8月16日下午洗牙");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("2026-08-16下午暂时没有可用号源")).toBeVisible();

  const quickReply = page.getByRole("button", { name: "查看未来 7 天可约时段" });
  await expect(quickReply).toBeVisible();
  await quickReply.click();
  await expect(page.getByLabel("输入预约需求")).toHaveValue("有哪些日期可约");
  await expect(page.getByRole("heading", { name: "请选择预约时段" })).toHaveCount(0);

  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("从 2026-08-16 起未来 7 天找到 1 个可约时段，请选择。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "请选择预约时段" })).toBeVisible();
  await expect(page.locator(".option-row")).toHaveCount(1);
  await expect(quickReply).toHaveCount(0);
});

test("初始空会话在宽屏提供紧凑引导、受限内容轨与可折叠导航", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 2048, height: 1280 });
  await signIn(page);

  await expect(page.getByRole("heading", { name: "我可以帮您处理本人的预约" })).toBeVisible();
  await expect(page.getByText("尚未开始 Agent Run")).toHaveCount(0);

  const composerWidth = await page.locator(".composer__content").evaluate((element) => element.getBoundingClientRect().width);
  expect(composerWidth).toBeLessThanOrEqual(960);
  const promptBox = await page.locator(".prompt-list").boundingBox();
  const composerBox = await page.locator(".composer").boundingBox();
  expect(promptBox).not.toBeNull();
  expect(composerBox).not.toBeNull();
  expect(composerBox!.y - (promptBox!.y + promptBox!.height)).toBeLessThanOrEqual(48);
  const screenshot = testInfo.outputPath("initial-empty-workspace.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("initial-empty-workspace", { path: screenshot, contentType: "image/png" });

  await page.getByRole("button", { name: "创建预约" }).click();
  await expect(page.getByRole("heading", { name: "请选择服务项目" })).toBeVisible();
  await expect(page.getByText("尚未开始 Agent Run")).toHaveCount(0);

  await page.getByRole("button", { name: "收起会话导航" }).click();
  await expect(page.locator(".workspace")).toHaveClass(/workspace--nav-collapsed/);
  await expect(page.getByRole("button", { name: "展开会话导航" })).toBeVisible();
});

test("人工客服使用真实任务 API 领取、处理并交还 Agent", async ({ page }, testInfo) => {
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想预约2026年8月16日上午洗牙");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "请选择预约时段" })).toBeVisible();
  await page.getByRole("button", { name: "请求人工客服" }).click();
  await expect(page.getByText("当前已由人工客服接管")).toBeVisible();

  await signInAs(page, "operator");
  await expect(page.getByRole("heading", { name: "人工客服工作台" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "患者请求人工" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "患者说了什么" })).toBeVisible();
  await expect(page.getByText("我想预约2026年8月16日上午洗牙")).toBeVisible();
  await page.getByRole("button", { name: "领取任务" }).click();
  await page.getByLabel("向患者回复").fill("您好，我已收到您的预约请求，正在为您处理。");
  await page.getByRole("button", { name: "发送给患者" }).click();
  await expect(page.getByLabel("患者说了什么").getByText("您好，我已收到您的预约请求，正在为您处理。")).toBeVisible();
  await page.getByLabel("处理说明").fill("已核实患者诉求，等待 Agent 继续处理。");
  await page.getByRole("button", { name: "记录处理完成" }).click();
  await page.getByRole("button", { name: "交还 Agent" }).click();
  await page.getByRole("button", { name: "确认交还 Agent" }).click();
  await expect(page.getByText("任务已交还 Agent")).toBeVisible();
  const screenshot = testInfo.outputPath("operator-workspace.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("operator-workspace", { path: screenshot, contentType: "image/png" });
});

test("取消预约必须先选择列表项，再二次确认", async ({ page }) => {
  await signIn(page);

  await page.getByLabel("输入预约需求").fill("我想预约2026年8月16日上午洗牙");
  await page.getByRole("button", { name: "发送" }).click();
  await page.locator(".option-row").first().click();
  await page.getByRole("button", { name: "确认预约" }).click();
  await expect(page.getByText("预约已成功")).toBeVisible();

  await page.getByLabel("输入预约需求").fill("我想取消我的预约");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "请选择要处理的预约" })).toBeVisible();
  await expect(page.getByText("选择后会展示取消确认信息；此操作不会立即取消预约。")).toBeVisible();
  await page.getByRole("listitem").filter({ hasText: "2026年8月16日 10:00" }).getByRole("button", { name: "取消此预约" }).click();
  await expect(page.getByRole("heading", { name: "请确认以下取消预约信息" })).toBeVisible();
  await page.getByRole("button", { name: "确认取消预约" }).click();
  await expect(page.getByText("预约已取消")).toBeVisible();
});

test("管理员使用真实只读 API 查看运营总览与运行诊断", async ({ page }, testInfo) => {
  await signIn(page);
  await page.getByLabel("输入预约需求").fill("我想看牙");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.locator(".message--agent")).toHaveCount(2);

  await signInAs(page, "admin");
  await expect(page.getByRole("heading", { name: "运营管理工作台" })).toBeVisible();
  await expect(page.getByRole("main", { name: "运营总览" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "预约服务运行概览" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "创建预约转化流程" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "现在需要关注什么" })).toBeVisible();
  const overview = testInfo.outputPath("admin-overview.png");
  await page.screenshot({ path: overview, fullPage: true });
  await testInfo.attach("admin-overview", { path: overview, contentType: "image/png" });
  await page.getByRole("button", { name: "运行诊断", exact: true }).click();
  await expect(page.getByRole("heading", { name: "运行记录" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "运行时间线" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "最近运行事件" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送" })).toHaveCount(0);
  const screenshot = testInfo.outputPath("admin-workspace.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("admin-workspace", { path: screenshot, contentType: "image/png" });
});

test("桌面与窄屏均不产生水平页面溢出，关键地标可通过键盘聚焦", async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await signIn(page);
    expect(await page.locator("html").evaluate((element) => element.scrollWidth <= window.innerWidth)).toBeTruthy();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.reload();
  }
});
