#!/usr/bin/env python3
import os
import json
import xml.etree.ElementTree as ET
from git import Repo
from pathlib import Path

def find_ros_packages():
    """递归查找所有ROS包并返回路径-包名映射"""
    packages = {}
    # 单包检测（根目录有package.xml）
    if Path("package.xml").exists():
        tree = ET.parse("package.xml")
        name = tree.findtext("name")
        packages["."] = name
    else:
        # 多包递归查找
        for root, _, files in os.walk("."):
            if "package.xml" in files:
                try:
                    tree = ET.parse(Path(root) / "package.xml")
                    name = tree.findtext("name")
                    packages[root] = name
                except ET.ParseError:
                    print(f"警告: {root}/package.xml 解析失败，跳过")
    return packages

def sync_to_branch(repo, branch, files, commit, pr_num=None):
    """同步修改到指定分支"""
    # 创建工作树
    tmp_dir = Path(f"worktree_{branch.replace('/', '_')}")
    tmp_dir.mkdir(exist_ok=True)
    
    # 检出分支到临时目录
    worktree = Repo.init(tmp_dir)
    worktree.git.worktree("add", "-f", tmp_dir, branch)
    
    # 复制修改的文件
    for file in files:
        src = Path(file)
        dst = tmp_dir / file
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(src, "rb") as f_src, open(dst, "wb") as f_dst:
            f_dst.write(f_src.read())
    
    # 提交变更
    worktree.git.add(A=True)
    if worktree.is_dirty():
        msg = f"{commit.message.strip()}\nSource: {commit.hexsha}"
        if pr_num: msg += f" | PR: #{pr_num}"
        worktree.index.commit(msg)
        worktree.git.push("origin", branch)
        print(f"✅ 已同步到 {branch}")
    else:
        print(f"⏭️ {branch} 无变更需提交")
    
    # 清理工作树
    worktree.git.worktree("remove", tmp_dir)

def main():
    # 初始化仓库
    repo = Repo(".")
    base_commit = os.getenv("GITHUB_BASE_REF", "HEAD~1")
    head_commit = os.getenv("GITHUB_SHA", "HEAD")
    
    # 1. 获取包映射
    packages = find_ros_packages()
    print(f"📦 发现 {len(packages)} 个ROS包: {json.dumps(packages, indent=2)}")
    
    # 2. 检查PR号（如果是PR合并）
    merge_msg = repo.head.commit.message
    pr_num = None
    if "Merge pull request" in merge_msg:
        pr_num = merge_msg.split("#")[1].split()[0]  # 提取PR号
    
    # 3. 处理每个提交
    commits = list(repo.iter_commits(f"{base_commit}..{head_commit}"))
    print(f"🔍 处理 {len(commits)} 个提交")
    
    for commit in commits:
        changed_files = [item.a_path for item in commit.diff(commit.parents[0])]
        affected_branches = {}
        
        # 4. 匹配受影响的包
        for file in changed_files:
            for path, pkg_name in packages.items():
                if path == ".":
                    if "/" not in file:  # 根目录包匹配无路径文件
                        branch = f"debian/jazzy/noble/{pkg_name}"
                        affected_branches.setdefault(branch, set()).add(file)
                elif file.startswith(path + "/"):
                    branch = f"debian/jazzy/noble/{pkg_name}"
                    affected_branches.setdefault(branch, set()).add(file)
        
        # 5. 同步到分支
        for branch, files in affected_branches.items():
            print(f"🔄 同步 {branch}: {len(files)} 个文件")
            sync_to_branch(repo, branch, files, commit, pr_num)

if __name__ == "__main__":
    main()