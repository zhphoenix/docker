# WSL Docker 空间释放指南

> 适用环境：
>
> - Windows 11
> - WSL2
> - Docker Desktop
> - Ubuntu（或其他 Linux 发行版）

---

# 一、为什么 Docker 删除后空间没有释放？

Docker Desktop 在 WSL2 中使用 **ext4.vhdx** 虚拟磁盘保存所有数据。

例如：

```
Images
Containers
Volumes
Build Cache
Overlay2
```

即使删除了镜像或容器：

- Windows 磁盘空间不会立即减少
- ext4.vhdx 不会自动缩小

因此，需要完成三个步骤：

```
清理 Docker 数据
        │
        ▼
关闭 WSL
        │
        ▼
压缩 ext4.vhdx
```

---

# 二、查看 Docker 占用空间

查看各类资源占用情况：

```bash
docker system df
```

示例：

```
TYPE            TOTAL    ACTIVE    SIZE      RECLAIMABLE
Images          25       8         95GB      60GB
Containers      12       2         8GB       7GB
Local Volumes   18       5         40GB      20GB
Build Cache     35                 15GB      15GB
```

说明：

| 类型 | 含义 |
|------|------|
| Images | Docker 镜像 |
| Containers | 容器 |
| Local Volumes | 数据卷 |
| Build Cache | Docker Build 缓存 |

---

# 三、清理 Docker 资源

## 1. 删除停止运行的容器

```bash
docker container prune
```

---

## 2. 删除未使用的镜像

```bash
docker image prune -a
```

作用：

- 删除所有未被容器使用的镜像
- 可释放大量磁盘空间

---

## 3. 删除 Build Cache

```bash
docker builder prune -a
```

适用于经常执行：

```bash
docker build
```

缓存可能占用几十 GB。

---

## 4. 删除未使用的数据卷

查看 Volume：

```bash
docker volume ls
```

删除未使用的数据卷：

```bash
docker volume prune
```

> **注意：**
>
> 如果 PostgreSQL、MinIO、Qdrant 等数据库使用 Docker Volume 保存数据，请确认数据卷未被使用后再删除。

---

## 5. 一键清理所有未使用资源

```bash
docker system prune -a --volumes
```

或：

```bash
docker system prune -af --volumes
```

将删除：

- 未使用镜像
- 停止容器
- Build Cache
- 未使用网络
- 未使用 Volume

---

# 四、查看 Docker 实际目录大小

Docker 默认目录：

```bash
/var/lib/docker
```

查看各目录占用：

```bash
du -sh /var/lib/docker/*
```

示例：

```
80G overlay2
15G volumes
3G image
```

通常占用最大的目录：

```
/var/lib/docker/overlay2
```

说明：

| 目录 | 内容 |
|------|------|
| overlay2 | 镜像层与容器层 |
| volumes | 数据卷 |
| image | 镜像元数据 |
| containers | 容器配置 |

---

# 五、关闭 WSL

在 Windows PowerShell 中执行：

```powershell
wsl --shutdown
```

查看 WSL 状态：

```powershell
wsl -l -v
```

应显示：

```
Stopped
```

---

# 六、压缩 WSL 虚拟磁盘

## 查看发行版

```powershell
wsl -l -v
```

例如：

```
Ubuntu-22.04
docker-desktop
docker-desktop-data
```

---

## 压缩 Docker 数据盘

```powershell
wsl --manage docker-desktop-data --compact
```

---

## 压缩 Ubuntu 数据盘

```powershell
wsl --manage Ubuntu-22.04 --compact
```

完成后：

```
ext4.vhdx
150GB
↓

60GB
```

Windows 磁盘空间将真正释放。

---

# 七、ext4.vhdx 的位置

通常位于：

```
C:\Users\<用户名>\AppData\Local\Docker\wsl\
```

或：

```
%LOCALAPPDATA%\Docker\wsl\
```

Ubuntu 的虚拟磁盘通常位于：

```
%LOCALAPPDATA%\Packages\
```

对应 Ubuntu 的目录下。

---

# 八、AI 项目注意事项

如果 AI 模型存放于：

```
/mnt/g/models
```

或 Windows 磁盘：

```
G:\models
```

这些文件：

- 不在 Docker 镜像中
- 不在 WSL ext4.vhdx 中
- 清理 Docker 不会删除模型
- 压缩 WSL 也不会影响模型

建议将大型模型始终存放在 Windows 独立磁盘中，以减少 WSL 虚拟磁盘占用。

---

# 九、安全清理流程（推荐）

## 第一步：查看占用

```bash
docker system df
```

---

## 第二步：删除停止容器

```bash
docker container prune
```

---

## 第三步：删除未使用镜像

```bash
docker image prune -a
```

---

## 第四步：删除 Build Cache

```bash
docker builder prune -a
```

---

## 第五步：删除未使用 Volume

```bash
docker volume prune
```

---

## 第六步：关闭 WSL

```powershell
wsl --shutdown
```

---

## 第七步：压缩 Docker

```powershell
wsl --manage docker-desktop-data --compact
```

---

## 第八步：压缩 Ubuntu（可选）

```powershell
wsl --manage Ubuntu-22.04 --compact
```

---

# 十、常用命令速查

| 功能 | 命令 |
|------|------|
| 查看 Docker 占用 | `docker system df` |
| 删除停止容器 | `docker container prune` |
| 删除未使用镜像 | `docker image prune -a` |
| 删除 Build Cache | `docker builder prune -a` |
| 删除未使用 Volume | `docker volume prune` |
| 一键清理 Docker | `docker system prune -af --volumes` |
| 查看 Docker 目录大小 | `du -sh /var/lib/docker/*` |
| 查看 WSL 状态 | `wsl -l -v` |
| 关闭 WSL | `wsl --shutdown` |
| 压缩 Docker 数据盘 | `wsl --manage docker-desktop-data --compact` |
| 压缩 Ubuntu 数据盘 | `wsl --manage Ubuntu-22.04 --compact` |

---

# 十一、推荐维护策略（AI 开发环境）

建议每月或在大规模构建镜像后执行以下维护流程：

```bash
# 查看空间占用
docker system df

# 清理停止容器
docker container prune

# 清理未使用镜像
docker image prune -a

# 清理构建缓存
docker builder prune -a

# 清理未使用 Volume
docker volume prune
```

随后，在 Windows PowerShell 中执行：

```powershell
# 关闭 WSL
wsl --shutdown

# 压缩 Docker 数据盘
wsl --manage docker-desktop-data --compact

# （可选）压缩 Ubuntu 数据盘
wsl --manage Ubuntu-22.04 --compact
```

---

# 十二、总结

完整的 Docker 空间释放流程如下：

```text
查看空间占用
        │
        ▼
清理容器
        │
        ▼
清理镜像
        │
        ▼
清理 Build Cache
        │
        ▼
清理 Volume
        │
        ▼
关闭 WSL
        │
        ▼
压缩 ext4.vhdx
        │
        ▼
Windows 磁盘空间真正释放
```

对于 AI 开发环境，建议：

- 模型文件存放在独立磁盘（如 `G:\models`）
- 定期清理 Docker 镜像和缓存
- 定期压缩 WSL 虚拟磁盘
- 对 PostgreSQL、Qdrant、MinIO 等重要数据卷做好备份，避免误删