#!/usr/bin/env python3
import os
import argparse
import json
import subprocess
import xml.etree.ElementTree as ET
from git import Repo, GitCommandError
from pathlib import Path

def find_ros_packages():
    """递归查找所有ROS包并返回路径-包名映射"""
    packages = {}
    if Path("package.xml").exists():
        tree = ET.parse("package.xml")
        name = tree.findtext("name")
        packages["."] = name
    else:
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

def create_pull_request(target_branch, source_branch, commit, pr_num=None):
    title = f"Auto-sync: {commit.hexsha[:7]}"
    body = f"Source commit: {commit.hexsha}\nMessage: {commit.message.strip()}"
    if pr_num:
        body += f"\nOriginal PR: #{pr_num}"
    
    try:
        result = subprocess.run(
            ["gh", "pr", "create", 
             "--base", target_branch,
             "--head", source_branch,
             "--title", title,
             "--body", body,
             "--fill"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ PR创建成功: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ PR创建失败: {e.stderr}")
        return None

def sync_commit_to_branch(repo, base_branch, target_branch, commit, files, mode = "pr"):
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

            if mode == "direct":
                worktree_repo.git.push("origin", target_branch)
                print(f"✅ 已同步提交 {commit.hexsha[:7]} 到 {target_branch}")
            else:
                temp_branch = f"sync-{target_branch.replace('/', '-')}-{commit.hexsha[:7]}"
                worktree_repo.git.checkout("-b", temp_branch)
                worktree_repo.git.push("origin", temp_branch, force=True)
                pr_url = create_pull_request(target_branch, temp_branch, commit, pr_num)
                if pr_url:
                    print(f"✅ PR已创建: {pr_url}")
        else:
            print(f"⏭️ {target_branch} 无变更需提交")
    
    except GitCommandError as e:
        print(f"❌ 同步失败: {str(e)}")
    finally:
        # 清理工作树
        if worktree_path.exists():
            repo.git.worktree("remove", worktree_dir, "--force")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Sync source to debian branch.")
    parser.add_argument("--mode", choices=["pr", "direct"], default="pr",
                        help="Sync mode, pr=Create a pull request(default), direct=Push to debian branch.")
    parser.add_argument("--path", type=str, default=".",
                        help="Path of workspace, default: current directory.")
    return parser.parse_args()

def main():
    args = parse_arguments()
    # Init repo
    repo = Repo(args.path)
 
    # 1. Get packages
    packages = find_ros_packages()
    print(f"📦 Find {len(packages)} ROS pakages: {json.dumps(packages, indent=2)}")

    # 2. Get commits
    before_sha = os.getenv("GITHUB_EVENT_BEFORE")
    after_sha = os.getenv("GITHUB_SHA")
    print(f"before_sha:{before_sha}, after_sha:{after_sha}")

    if not before_sha or before_sha == "0"*40:  # Initial commit
        commits = [repo.commit(after_sha)]
    else:
        commits = list(repo.iter_commits(f"{before_sha}..{after_sha}"))
    
    print(f"🔍 Handle {len(commits)} commits.")
    print(f"commits: {commits}")

    # 3. Process
    for commit in commits:
        try:
            # Get changed file list
            changed_files = [item.a_path for item in commit.diff(commit.parents[0])]
            print(f"chagned files: {changed_files}")
            affected_branches = {}
            
            # 4. Match packages
            for file in changed_files:
                for path, pkg_name in packages.items():
                    normalized_path = path[2:] if path.startswith("./") else path
                    print(f"normalized_path:{normalized_path}, pkg_name:{pkg_name}, file:{file}")

                    if normalized_path == ".":
                        if "/" not in file or file.startswith("./"):
                            branch = f"debian/jazzy/noble/{pkg_name}"
                            affected_branches.setdefault(branch, set()).add(file)
                    else:
                        if file.startswith(normalized_path + "/") or file == normalized_path:
                            branch = f"debian/jazzy/noble/{pkg_name}"
                            affected_branches.setdefault(branch, set()).add(file)
            
            for branch, files in affected_branches.items():
                print(f"🔄 Sync {branch}: {len(files)} files")
                sync_commit_to_branch(repo, "main", branch, commit, files, mode = args.mode)
        
        except IndexError:  # 初始提交无父提交
            print(f"⚠️ 初始提交 {commit.hexsha} 跳过文件比对")

if __name__ == "__main__":
    main()