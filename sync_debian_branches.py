#!/usr/bin/env python3
import os
import json
import xml.etree.ElementTree as ET
from git import Repo, GitCommandError
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
        for root, dirs, files in os.walk("."):
            if "package.xml" in files:
                try:
                    tree = ET.parse(Path(root) / "package.xml")
                    name = tree.findtext("name")
                    packages[root] = name
                    dirs.clear()
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

def sync_commit_to_branch(repo, base_branch, target_branch, commit, files):
    """将单个提交同步到目标分支"""
    # 创建工作树
    worktree_dir = f"worktree_{target_branch.replace('/', '_')}"
    worktree_path = Path(worktree_dir)
    
    try:
        # 创建并检出工作树
        repo.git.worktree("add", worktree_dir, target_branch)
        worktree_repo = Repo(worktree_path)
        
        # 检出目标文件
        for file in files:
            src_path = Path(file)
            dst_path = worktree_path / file
            
            # 确保目录存在
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 从源提交复制文件
            repo.git.checkout(commit.hexsha, "--", file)
            if src_path.exists():
                with open(src_path, "rb") as f_src, open(dst_path, "wb") as f_dst:
                    f_dst.write(f_src.read())
        
        # 提交变更
        worktree_repo.git.add(A=True)
        if worktree_repo.is_dirty():
            # 保留原始提交信息
            original_msg = commit.message.strip()
            commit_msg = f"{original_msg}\nSource: {commit.hexsha}"
            
            # 添加PR引用（如果存在）
            if "Merge pull request" in original_msg:
                pr_num = original_msg.split("#")[1].split()[0]
                commit_msg += f" | PR: #{pr_num}"
            
            worktree_repo.index.commit(commit_msg)
            worktree_repo.git.push("origin", target_branch)
            print(f"✅ 已同步提交 {commit.hexsha[:7]} 到 {target_branch}")
        else:
            print(f"⏭️ {target_branch} 无变更需提交")
    
    except GitCommandError as e:
        print(f"❌ 同步失败: {str(e)}")
    finally:
        # 清理工作树
        if worktree_path.exists():
            repo.git.worktree("remove", worktree_dir, "--force")

def main():
    # 初始化仓库
    repo = Repo(".")
    base_commit = os.getenv("GITHUB_BASE_REF", "HEAD~1")
    head_commit = os.getenv("GITHUB_SHA", "HEAD")

    print(f"base_commit:${base_commit}, head_commit:{head_commit}")
 
    # 1. 获取包映射
    packages = find_ros_packages()
    print(f"📦 发现 {len(packages)} 个ROS包: {json.dumps(packages, indent=2)}")

    # 2. 获取提交范围
    before_sha = os.getenv("GITHUB_EVENT_BEFORE")
    after_sha = os.getenv("GITHUB_SHA")
    print(f"before_sha:{before_sha}, after_sha:{after_sha}")

    if not before_sha or before_sha == "0"*40:  # 初始提交情况
        commits = [repo.commit(after_sha)]
    else:
        commits = list(repo.iter_commits(f"{before_sha}..{after_sha}"))
    
    print(f"🔍 处理 {len(commits)} 个提交")
    print(f"commits: {commits}")


    # 3. 处理每个提交
    for commit in commits:
        try:
            # 获取变更文件列表
            changed_files = [item.a_path for item in commit.diff(commit.parents[0])]
            print(f"chagned files: {changed_files}")
            affected_branches = {}
            
            # 4. 匹配受影响的包
            for file in changed_files:
                for path, pkg_name in packages.items():
                    print(f"path:{path}, pkg_name:{pkg_name}, file:{file}")
                    # 精确路径匹配逻辑
                    if path == ".":
                        # 根目录包匹配无路径文件
                        if "/" not in file or file.startswith("./"):
                            branch = f"debian/jazzy/noble/{pkg_name}"
                            affected_branches.setdefault(branch, set()).add(file)
                    else:
                        # 子目录包匹配
                        normalized_path = path + "/"
                        if file.startswith(normalized_path) or file == path:
                            branch = f"debian/jazzy/noble/{pkg_name}"
                            affected_branches.setdefault(branch, set()).add(file)
            
            # 5. 同步到各分支
            for branch, files in affected_branches.items():
                print(f"🔄 同步 {branch}: {len(files)} 个文件")
                sync_commit_to_branch(repo, "main", branch, commit, files)
        
        except IndexError:  # 初始提交无父提交
            print(f"⚠️ 初始提交 {commit.hexsha} 跳过文件比对")


    # # 2. 检查PR号（如果是PR合并）
    # merge_msg = repo.head.commit.message
    # pr_num = None
    # if "Merge pull request" in merge_msg:
    #     pr_num = merge_msg.split("#")[1].split()[0]  # 提取PR号
    
    # 3. 处理每个提交
    # commits = list(repo.iter_commits(f"{base_commit}..{head_commit}"))
    # print(f"🔍 处理 {len(commits)} 个提交")
    
    # for commit in commits:
    #     changed_files = [item.a_path for item in commit.diff(commit.parents[0])]
    #     affected_branches = {}
        
    #     # 4. 匹配受影响的包
    #     for file in changed_files:
    #         for path, pkg_name in packages.items():
    #             if path == ".":
    #                 if "/" not in file:  # 根目录包匹配无路径文件
    #                     branch = f"debian/jazzy/noble/{pkg_name}"
    #                     affected_branches.setdefault(branch, set()).add(file)
    #             elif file.startswith(path + "/"):
    #                 branch = f"debian/jazzy/noble/{pkg_name}"
    #                 affected_branches.setdefault(branch, set()).add(file)
        
    #     # 5. 同步到分支
    #     for branch, files in affected_branches.items():
    #         print(f"🔄 同步 {branch}: {len(files)} 个文件")
    #         sync_to_branch(repo, branch, files, commit, pr_num)

if __name__ == "__main__":
    main()