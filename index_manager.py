import datetime
import logging
import os

import faiss
import numpy as np

from database import get_image_id_path_features
from models import DatabaseSession

logger = logging.getLogger(__name__)

FEATURE_DIM = 512  # chinese-clip-vit-base-patch16 特征维度


class FeatureIndex:
    """管理图片特征的FAISS索引和内存缓存"""

    def __init__(self, index_dir="features_index"):
        self.index_dir = index_dir
        self.ids = None          # np.array of int64, shape (n,)
        self.paths = None        # list[str], 长度 n
        self.modify_times = None  # list[datetime | None], 长度 n
        self.features = None     # np.array float32, shape (n, FEATURE_DIM)
        self.faiss_index = None  # faiss.IndexFlatIP
        self._loaded = False
        os.makedirs(index_dir, exist_ok=True)

    def load(self):
        """从磁盘加载索引，如果磁盘文件不存在则从数据库构建"""
        ids_path = os.path.join(self.index_dir, "ids.npy")
        features_path = os.path.join(self.index_dir, "features.npy")
        paths_path = os.path.join(self.index_dir, "paths.npy")
        faiss_path = os.path.join(self.index_dir, "image.index")

        if os.path.exists(ids_path) and os.path.exists(features_path) and os.path.exists(faiss_path):
            try:
                logger.info("从磁盘加载特征索引...")
                self.ids = np.load(ids_path)
                self.features = np.load(features_path)
                self.paths = np.load(paths_path, allow_pickle=True).tolist()
                self.faiss_index = faiss.read_index(faiss_path)

                # 加载 modify_times（如果存在）
                mt_path = os.path.join(self.index_dir, "modify_times.npy")
                if os.path.exists(mt_path):
                    self.modify_times = np.load(mt_path, allow_pickle=True).tolist()
                else:
                    self.modify_times = [None] * len(self.ids)

                self._loaded = True
                logger.info(f"特征索引加载完成，共 {len(self.ids)} 张图片")
                return
            except Exception as e:
                logger.warning(f"从磁盘加载索引失败: {e}，将从数据库重建")

        # 磁盘文件不存在，从数据库构建
        self.build_from_db()

    def build_from_db(self):
        """从数据库构建索引"""
        logger.info("从数据库构建特征索引...")
        with DatabaseSession() as session:
            id_list, path_list, features_list = get_image_id_path_features(session)

        if not id_list:
            logger.warning("数据库中无图片数据")
            self.ids = np.array([], dtype=np.int64)
            self.paths = []
            self.modify_times = []
            self.features = np.zeros((0, FEATURE_DIM), dtype=np.float32)
            self.faiss_index = faiss.IndexFlatIP(FEATURE_DIM)
            self._loaded = True
            return

        self.ids = np.array(id_list, dtype=np.int64)
        self.paths = list(path_list)
        self.modify_times = [None] * len(self.ids)

        # 二进制 BLOB → numpy float32 矩阵
        self.features = np.frombuffer(
            b"".join(features_list), dtype=np.float32
        ).reshape(len(features_list), -1).copy()  # copy() 避免只读buffer

        # 构建 FAISS 内积索引
        self.faiss_index = faiss.IndexFlatIP(FEATURE_DIM)
        self.faiss_index.add(self.features.astype(np.float32))

        self._loaded = True
        self._save_to_disk()
        logger.info(f"特征索引构建完成，共 {len(self.ids)} 张图片")

    def _save_to_disk(self):
        """保存索引到磁盘"""
        if self.ids is None or len(self.ids) == 0:
            return
        np.save(os.path.join(self.index_dir, "ids.npy"), self.ids)
        np.save(os.path.join(self.index_dir, "features.npy"), self.features)
        np.save(os.path.join(self.index_dir, "paths.npy"), np.array(self.paths, dtype=object))
        if self.modify_times:
            np.save(os.path.join(self.index_dir, "modify_times.npy"), np.array(self.modify_times, dtype=object))
        faiss.write_index(self.faiss_index, os.path.join(self.index_dir, "image.index"))

    def rebuild(self):
        """重新从数据库构建索引（扫描完成后调用）"""
        logger.info("重建特征索引...")
        self.build_from_db()

    def search(self, positive_feature, negative_feature, positive_threshold, negative_threshold,
               filter_path="", start_time=None, end_time=None):
        """
        搜索相似图片
        Returns: list[(id, path, score)]，按 score 降序排列
        """
        if not self._loaded or self.ids is None or len(self.ids) == 0:
            return []

        has_filter = bool(filter_path) or start_time is not None or end_time is not None

        if has_filter:
            # 有过滤条件：构建布尔掩码在内存中过滤
            mask = np.ones(len(self.ids), dtype=bool)
            if filter_path:
                mask &= np.array([filter_path in p for p in self.paths], dtype=bool)
            if start_time is not None:
                start_dt = datetime.datetime.fromtimestamp(start_time)
                mask &= np.array(
                    [mt is not None and mt >= start_dt for mt in self.modify_times],
                    dtype=bool
                )
            if end_time is not None:
                end_dt = datetime.datetime.fromtimestamp(end_time)
                mask &= np.array(
                    [mt is not None and mt <= end_dt for mt in self.modify_times],
                    dtype=bool
                )

            if not np.any(mask):
                return []

            filtered_features = self.features[mask]
            filtered_ids = self.ids[mask]
            filtered_paths = [p for p, m in zip(self.paths, mask) if m]

            scores = self._compute_scores(
                positive_feature, negative_feature, filtered_features,
                positive_threshold, negative_threshold
            )
            results = []
            for i, score in enumerate(scores):
                if score > 0:
                    results.append((int(filtered_ids[i]), filtered_paths[i], float(score)))
        else:
            # 无过滤条件：直接用 FAISS 快速搜索
            if positive_feature is not None:
                query = positive_feature.astype(np.float32)
                if query.ndim == 1:
                    query = query.reshape(1, -1)
                top_k = len(self.ids)
                distances, indices = self.faiss_index.search(query, top_k)

                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    if idx < 0:
                        continue
                    score = float(dist)
                    if score < positive_threshold / 100:
                        continue
                    # 反向特征过滤
                    if negative_feature is not None:
                        neg_score = float(self.features[idx] @ negative_feature.T)
                        if neg_score > negative_threshold / 100:
                            continue
                    results.append((int(self.ids[idx]), self.paths[idx], score))
            else:
                # 没有正向特征，全部打分为1
                scores = self._compute_scores(
                    positive_feature, negative_feature, self.features,
                    positive_threshold, negative_threshold
                )
                results = []
                for i, score in enumerate(scores):
                    if score > 0:
                        results.append((int(self.ids[i]), self.paths[i], float(score)))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def _compute_scores(self, positive_feature, negative_feature, features, positive_threshold, negative_threshold):
        """
        计算分数，逻辑与 process_assets.match_batch 完全一致
        """
        if positive_feature is None:
            positive_scores = np.ones(len(features))
        else:
            positive_scores = features @ positive_feature.T

        negative_scores = None
        if negative_feature is not None:
            negative_scores = features @ negative_feature.T

        scores = np.where(positive_scores < positive_threshold / 100, 0, positive_scores)
        if negative_feature is not None:
            scores = np.where(negative_scores > negative_threshold / 100, 0, scores)

        # positive_feature 为 None 时 scores 是一维 (n,)
        # 正常矩阵乘法时 scores 通常是二维 (n, 1)
        # 统一打平成一维，兼容两种情况
        return np.asarray(scores).reshape(-1)


# 模块级单例
_feature_index = None


def get_feature_index() -> FeatureIndex:
    """获取全局 FeatureIndex 实例"""
    global _feature_index
    if _feature_index is None:
        _feature_index = FeatureIndex()
        _feature_index.load()
    return _feature_index


def rebuild_feature_index():
    """重建全局 FeatureIndex（扫描完成后调用）"""
    global _feature_index
    if _feature_index is not None:
        _feature_index.rebuild()
    else:
        _feature_index = FeatureIndex()
        _feature_index.load()
