(() => {
    "use strict";
    const steps = [
        {id:"register", title:"1 · 登记录像和事前查询", help:"可从空表单开始，或选择已保存的登记草稿。完整计划导出前请明确用途和是否看过模型结果。", file:"登记草稿或没有人工判断的旧计划（可选）", button:"打开登记表单"},
        {id:"references", title:"2 · 看原片，登记人工参考", help:"选择登记表单导出的计划，也可从已有人工参考的计划开始。核对实际原片后打开标注页，来源与查询保持不变。", file:"待核对计划", button:"核对原片并打开标注页"},
        {id:"references-import", title:"3 · 保存并核对原片标注", help:"选择标注页下载的记录。再次核对原片身份和来源声明，生成待冻结计划；未确认的参考保持未确认。", file:"原片标注记录", button:"核对标注记录"},
        {id:"freeze", title:"4 · 冻结来源、查询与参考", help:"保存事前资料和实际原片身份。准备不足时说明缺什么；冻结成功不会自动证明数据独立或验收通过。", button:"冻结已核对计划"},
        {id:"bind", title:"5 · 关联已完成的分析", help:"选择已有分析项目、来源与任务的对应表，以及要评估的用途。只读核对已有结果，不会开始视频分析。", file:"来源与任务对应表", button:"关联已完成分析"},
        {id:"ranking", title:"6 · 明确生成一次检索报告", help:"只在点击后按冻结查询搜索已有结果，保存原十位排名。混合与语义方式使用已有本机模型；不发送视觉分析，不付费。", button:"生成这次固定检索报告"},
        {id:"review", title:"7 · 回看固定十位，填写判断", help:"打开本次报告的候选评审页。缺位与重复不补位，可用评分必须对应事前参考；下载判断后回到这里计分。", button:"打开固定候选评审页"},
        {id:"score", title:"8 · 对原排名计分", help:"选择评审页下载的记录，按原排名计分，不再搜索。未判定仍未判定；未通过或未验证时报告照常保留。", file:"候选判断记录", button:"核对记录并计算原排名"}
    ];
    const required = {"references-import":"references", freeze:"references-import", bind:"freeze", ranking:"bind", review:"ranking", score:"review"};
    const states = {running:"正在执行", finished:"资料已保存", failed:"本次失败，资料已保留", interrupted:"执行已中断，资料已保留"};
    const byId = id => document.getElementById(id);
    let current = null, revision = 0, controller = null, timer = null;
    const text = (tag, value, className) => {const node=document.createElement(tag); node.textContent=value; if(className) node.className=className; return node;};
    function status(message) {byId("status").textContent=message;}
    function resetRequest() {revision+=1; controller?.abort(); controller=new AbortController(); clearTimeout(timer); return {version:revision, signal:controller.signal};}
    async function request(path, options={}) {
        const response=await fetch(path,{...options,headers:{"Content-Type":"application/json"}});
        const value=await response.json(); if(!response.ok) throw new Error(value.message || "读取失败，请保留资料后检查。"); return value;
    }
    function fileUrl(row, name) {return "/api/benchmark-file?"+new URLSearchParams({workflow:current.id,attempt:row.attemptId,file:name});}
    function appendLinks(parent,row) {
        const names=Object.keys(row.files || {}).filter(name => name.endsWith(".html") || ["draft.json","benchmark-plan.json","benchmark.json","freeze.json","record-template.json","benchmark-report.json","benchmark-fixed-report.json","reference-record.json","review-record.json"].includes(name));
        const labels={"edit.html":"打开登记表单","review.html":row.action==="references"?"打开原片标注页":"打开候选评审页","benchmark-fixed-report.json":"查看原排名评分报告","record-template.json":"下载空记录模板","draft.json":"下载登记草稿","benchmark-plan.json":"下载待冻结计划","freeze.json":"查看冻结资料","benchmark.json":"查看关联资料","benchmark-report.json":"查看固定检索报告","reference-record.json":"下载核对后的标注","review-record.json":"下载核对后的判断"};
        const links=text("div","","links"); for(const name of names){const link=text("a",labels[name] || name); link.href=fileUrl(row,name); if(name.endsWith(".html")){link.target="_blank";link.rel="noopener";}else{link.download=name;} links.append(link);} parent.append(links);
    }
    function inputLabel(form,label,id,type="text") {const wrapper=text("label",label), input=document.createElement("input");input.id=id;input.type=type; if(type==="file") input.accept=".json,application/json"; wrapper.append(input);form.append(wrapper);return input;}
    function selectLabel(form,label,id,values) {const wrapper=text("label",label),select=document.createElement("select");select.id=id;for(const [value,labelText] of values){const option=text("option",labelText);option.value=value;select.append(option);} wrapper.append(select);form.append(wrapper);return select;}
    function render(value) {
        current=value; byId("current").hidden=false;byId("current-name").textContent=value.name;
        byId("location").textContent="本机保存位置：artifacts/benchmark-workflows/"+value.id;
        const quality=value.qualityGate===true?"本报告检索质量达到门槛":value.qualityGate===false?"本报告未达到质量门槛":"检索质量尚未验证";
        byId("overall").textContent=(value.busy?"有一步正在执行。":"可以继续以下步骤。")+" · "+quality;
        const completed=Object.fromEntries(value.attempts.filter(row=>row.status==="finished").map(row=>[row.action,row]));
        byId("steps").replaceChildren();
        for(const [index,step] of steps.entries()) {
            const card=text("div","","step"), form=document.createElement("form");card.dataset.step=step.id;
            const latest=value.attempts.findLast(row=>row.action===step.id); card.append(text("h3",step.title),text("p",step.help));
            card.append(text("p",latest?states[latest.status] || "状态无法识别":"尚未执行","state"));
            const locked=value.busy || (required[step.id] && !completed[required[step.id]]) || steps.slice(index+1).some(next=>completed[next.id]);
            if(step.file) inputLabel(form,step.file,"input-"+step.id,"file");
            if(step.id==="bind") {inputLabel(form,"已有分析项目（例如 artifacts/demo-phase0）","bind-project");selectLabel(form,"本次用途","bind-partition",[["","请明确选择"],["development","开发练习"],["test","独立验收测试"]]);}
            if(step.id==="ranking") selectLabel(form,"检索方式","ranking-mode",[["hybrid","混合检索"],["lexical","词法检索"],["semantic","语义检索"]]);
            const button=text("button",step.button);button.type="submit";form.append(button);
            for(const input of form.querySelectorAll("input,select,button")) input.disabled=Boolean(locked);
            form.addEventListener("submit",event=>{event.preventDefault();void submit(step,form);});card.append(form);
            if(latest?.error) card.append(text("p",latest.error,"failed"));
            if(completed[step.id]) appendLinks(card,completed[step.id]); byId("steps").append(card);
        }
        byId("history").replaceChildren();for(const row of [...value.attempts].reverse()){const card=text("div","","record");card.append(text("p",`${steps.find(step=>step.id===row.action)?.title || row.action} · ${states[row.status]} · ${row.startedAt}`),text("p",`${row.attemptId} · ${row.elapsedMs==null?"耗时尚未保存":(row.elapsedMs/1000).toFixed(2)+"秒"}`)); if(row.error)card.append(text("p",row.error,"failed")); if(row.status==="finished")appendLinks(card,row);byId("history").append(card);}
        if(value.busy) timer=setTimeout(()=>void load(value.id,true),1000);
    }
    async function submit(step,form) {
        if(!current) return;
        const identity=current.id, guard=revision, fields={}; let activeRevision=guard;
        for(const node of form.querySelectorAll("input,select,button")) node.disabled=true;
        try {
            if(step.file) {const file=form.querySelector("input[type=file]").files[0];if(!file && step.id!=="register")throw new Error("请先选择本步骤所需的JSON文件。");if(file && file.size>4194304)throw new Error("资料最多4MiB，请保留原文件并检查。");fields.inputText=file?await file.text():"";}
            if(guard!==revision || current?.id!==identity) return;
            if(step.id==="bind"){fields.project=byId("bind-project").value;fields.partition=byId("bind-partition").value;}
            if(step.id==="ranking") fields.mode=byId("ranking-mode").value;
            const token=resetRequest(); activeRevision=token.version; status("正在提交这一步；输入及结果将保存在本机。");
            const value=await request("/api/benchmark-step",{method:"POST",body:JSON.stringify({workflow:identity,action:step.id,fields}),signal:token.signal});
            if(token.version!==revision || value.id!==identity) return;render(value);status("已提交。页面刷新或离开不会重新执行。");
        } catch(error) {if(activeRevision!==revision)return;status(error.message); if(current?.id===identity){for(const node of form.querySelectorAll("input,select,button"))node.disabled=false;}}
    }
    async function load(identifier,poll=false) {
        const token=resetRequest();
        try {const value=await request("/api/benchmark-workflow?"+new URLSearchParams({workflow:identifier}),{signal:token.signal});if(token.version!==revision || value.id!==identifier)return;
            // Polls keep file selections intact while work runs; replace only when status changes.
            if(!poll || JSON.stringify(value)!==JSON.stringify(current)) render(value);else if(value.busy)timer=setTimeout(()=>void load(identifier,true),1000);
            status(value.busy?"正在执行，可以离开后回来继续。":"已读取保存进度。表单中的修改仍需下载后提交。");
        }catch(error){if(token.version===revision){status(error.message);if(poll)timer=setTimeout(()=>void load(identifier,true),2000);}}
    }
    async function catalog(selected="") {
        const token=resetRequest();
        try {const data=await request("/api/benchmark-workflows",{signal:token.signal});if(token.version!==revision)return;
            const select=byId("workflow-select");select.replaceChildren();const empty=text("option","请选择");empty.value="";select.append(empty);
            for(const row of data.workflows){const option=text("option",row.name+" · "+row.createdAt);option.value=row.id;select.append(option);}
            if(selected && data.workflows.some(row=>row.id===selected)){select.value=selected;await load(selected);}else status(data.workflows.length?"请选择已保存流程，或新建流程。":"还没有保存的验收流程，可以从登记开始。");
        }catch(error){if(token.version===revision)status(error.message);}
    }
    byId("create-form").addEventListener("submit",event=>{event.preventDefault();void (async()=>{const token=resetRequest();byId("create-workflow").disabled=true;try{const value=await request("/api/benchmark-workflows",{method:"POST",body:JSON.stringify({name:byId("workflow-name").value}),signal:token.signal});if(token.version!==revision)return;location.hash=value.id;await catalog(value.id);}catch(error){if(token.version===revision)status(error.message);}finally{byId("create-workflow").disabled=false;}})();});
    byId("workflow-select").addEventListener("change",()=>{const id=byId("workflow-select").value;resetRequest();current=null;byId("current").hidden=true;location.hash=id;if(id)void load(id);});
    byId("refresh").addEventListener("click",()=>void catalog(current?.id || location.hash.slice(1)));
    void catalog(location.hash.slice(1));
})();
