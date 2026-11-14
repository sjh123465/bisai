"""种子数据初始化 — 灌入计算机学科基础知识点到 NetworkX 图谱
覆盖：数据结构、算法、计算机网络、操作系统、数据库
"""
import asyncio
from app.services.graph_service import get_graph
from app.services.vector_service import get_vector
from app.core.logger import get_logger

logger = get_logger("seed")


# 节点定义：(node_id, name, category, description)
NODES = [
    # ========== 数据结构 ==========
    ("ds_intro", "数据结构导论", "chapter", "数据结构是计算机存储、组织数据的方式。常见类型有线性结构和非线性结构。"),
    ("array", "数组", "structure", "连续内存存储的同类型元素集合，随机访问 O(1)，插入删除 O(n)"),
    ("linked_list", "链表", "structure", "由节点组成的线性结构，每个节点包含数据和指针，插入删除 O(1)，访问 O(n)"),
    ("singly_linked_list", "单链表", "structure", "链表的一种，每个节点只有一个后继指针，尾节点指针为 None"),
    ("doubly_linked_list", "双向链表", "structure", "每个节点有前驱和后继两个指针，可双向遍历"),
    ("stack", "栈", "structure", "后进先出 LIFO 的线性结构，可由数组或链表实现"),
    ("queue", "队列", "structure", "先进先出 FIFO 的线性结构，可由数组或链表实现"),
    ("deque", "双端队列", "structure", "两端都可进出的队列"),

    # ========== 树 ==========
    ("tree_intro", "树结构导论", "chapter", "树是由根节点和子树组成的分层结构"),
    ("binary_tree", "二叉树", "structure", "每个节点最多有两个子节点的树结构"),
    ("full_binary_tree", "满二叉树", "structure", "所有层的节点数都达到最大值的二叉树"),
    ("complete_binary_tree", "完全二叉树", "structure", "除最后一层外其余层都满，最后一层节点靠左排列的二叉树"),
    ("binary_search_tree", "二叉搜索树", "structure", "BST：左子树所有节点值 < 根值 < 右子树所有节点值，查找平均 O(log n)"),
    ("bst_insert", "BST 插入", "operation", "按照 BST 性质找到空位置插入新节点，平均 O(log n)"),
    ("bst_delete", "BST 删除", "operation", "BST 删除分三种情况：叶子节点、单子节点、双子节点（用后继替代）"),
    ("bst_search", "BST 查找", "operation", "根据值与当前节点比较，决定向左或向右子树递归/迭代查找"),

    ("avl_tree", "AVL 树", "structure", "自平衡二叉搜索树，任意节点左右子树高度差绝对值 ≤ 1，保证 O(log n)"),
    ("avl_rotation", "AVL 旋转", "operation", "单旋转和双旋转四种类型：LL、RR、LR、RL"),
    ("red_black_tree", "红黑树", "structure", "自平衡二叉搜索树，满足五个性质：根黑、叶黑、红节点子必黑、黑高相同。保证最长路径不超过最短路径两倍"),
    ("rbt_insert", "红黑树插入", "operation", "插入节点着色为红色，然后通过旋转和变色修复性质，最多两次旋转"),
    ("rbt_delete", "红黑树删除", "operation", "删除节点后需要修复红黑性质，比插入更复杂"),
    ("rotation", "旋转操作", "operation", "AVL 和红黑树的核心平衡操作，左旋和右旋两种基本形式"),

    ("heap", "堆", "structure", "完全二叉树 + 堆性质（大顶堆：父≥子，小顶堆：父≤子），常用于优先队列"),
    ("heapify", "堆化", "operation", "将数组调整为堆结构的过程，O(n) 时间复杂度"),
    ("heap_sort", "堆排序", "algorithm", "利用堆进行排序：建堆 → 取堆顶 → 重新堆化，时间 O(n log n)，空间 O(1)"),

    ("binary_tree_traversal", "二叉树遍历", "operation", "前序、中序、后序、层序四种遍历方式"),
    ("preorder", "前序遍历", "operation", "根-左-右顺序，常配合递归或栈实现"),
    ("inorder", "中序遍历", "operation", "左-根-右顺序，BST 的中序遍历是有序序列"),
    ("postorder", "后序遍历", "operation", "左-右-根顺序"),
    ("level_order", "层序遍历", "operation", "按层从上到下从左到右，配合队列实现 BFS"),

    # ========== 图 ==========
    ("graph_intro", "图结构导论", "chapter", "图 G=(V,E) 由顶点集 V 和边集 E 组成，分为有向图和无向图"),
    ("graph_representation", "图的存储", "operation", "邻接矩阵 O(V²) 和邻接表 O(V+E) 两种主要方式"),
    ("dfs", "深度优先搜索", "algorithm", "一条路走到黑再回溯，栈实现或递归实现，时间 O(V+E)"),
    ("bfs", "广度优先搜索", "algorithm", "一层一层扩散，队列实现，时间 O(V+E)，常用于最短路径"),
    ("shortest_path", "最短路径", "algorithm", "从起点到所有点的最短路径。有向有权用 Dijkstra/Floyd，无权用 BFS"),
    ("dijkstra", "Dijkstra 算法", "algorithm", "单源最短路径，贪心 + 优先队列，不能处理负权边，时间 O((V+E)log V)"),
    ("floyd", "Floyd-Warshall 算法", "algorithm", "多源最短路径，动态规划思想，可处理负权（不可有负环），时间 O(V³)"),
    ("min_spanning_tree", "最小生成树", "algorithm", "连通图中选出连通所有顶点且权值最小的树。Kruskal + 并查集，Prim + 堆"),
    ("kruskal", "Kruskal 算法", "algorithm", "按边权从小到大选边，若不构成环则加入生成树，配合并查集判环"),
    ("prim", "Prim 算法", "algorithm", "从一个顶点开始，每次选离生成树最近的顶点加入，配合堆加速"),
    ("union_find", "并查集", "structure", "支持快速合并和查找连通分量的数据结构，路径压缩 + 按秩合并后接近 O(α(n))"),
    ("topological_sort", "拓扑排序", "algorithm", "对 DAG 的顶点排序使得若有边 u→v 则 u 在 v 之前。Kahn 算法或 DFS 后序逆序"),

    # ========== 算法设计 ==========
    ("algo_intro", "算法设计导论", "chapter", "算法设计范式：分治、动态规划、贪心、回溯、分治") ,
    ("divide_and_conquer", "分治法", "paradigm", "分解 → 递归求解 → 合并。归并排序、快速排序、二分查找都是典型代表"),
    ("merge_sort", "归并排序", "algorithm", "分治：递归分解两半 → 分别排序 → 合并。时间稳定 O(n log n)，空间 O(n)，稳定排序"),
    ("quick_sort", "快速排序", "algorithm", "分治 + 随机化：选 pivot → 分区（小的放左大的放右）→ 递归。平均 O(n log n)，最坏 O(n²)，原地排序"),
    ("pivot", "基准值", "operation", "快排中用于分区的中间值，选择策略影响性能：固定首/尾、随机、三数取中"),
    ("partition", "分区操作", "operation", "快排核心步骤：以 pivot 为界，左侧小于等于，右侧大于。Lomuto 和 Hoare 两种方案"),
    ("binary_search", "二分查找", "algorithm", "在有序数组中折半查找目标值，时间 O(log n)，前提是数组有序"),

    ("dynamic_programming", "动态规划", "paradigm", "重叠子问题 + 最优子结构。自顶向下（记忆化）或自底向上（表格法）。经典问题：背包、最长公共子序列、编辑距离"),
    ("greedy", "贪心", "paradigm", "每步选当前最优，全局最优需满足贪心选择性质和最优子结构。活动选择、Huffman、Dijkstra 是典型"),
    ("backtracking", "回溯法", "paradigm", "暴力搜索 + 剪枝。深度优先遍历解空间树，不满足条件就回溯。N皇后、子集和、排列问题"),

    # ========== 复杂度分析 ==========
    ("complexity_intro", "复杂度导论", "chapter", "时间复杂度和空间复杂度是衡量算法效率的核心指标"),
    ("time_complexity", "时间复杂度", "concept", "用大 O 记号衡量算法执行时间随输入规模增长的渐近行为。常见：O(1)<O(log n)<O(n)<O(n log n)<O(n²)<O(2ⁿ)<O(n!)"),
    ("space_complexity", "空间复杂度", "concept", "衡量算法所需额外空间随输入规模增长的渐近行为"),
    ("asymptotic_notation", "渐近记号", "concept", "O(上界)、Ω(下界)、θ(紧上界)、o(严格上界)、ω(严格下界)"),

    # ========== 排序总结 ==========
    ("sort_summary", "排序算法对比", "chapter", "冒泡O(n²)/插排O(n²)/选择O(n²)/归并O(n log n)/快排平均O(n log n)/堆排O(n log n)/计数O(n+k)/基数O(k·n)"),
    ("bubble_sort", "冒泡排序", "algorithm", "相邻两两比较交换，稳定，原地，O(n²)，最好情况 O(n) 带优化"),
    ("insertion_sort", "插入排序", "algorithm", "像摸牌一样插入到有序部分，稳定，原地，O(n²)，小规模数据高效"),
    ("selection_sort", "选择排序", "algorithm", "每次选最小元素与开头交换，不稳定，原地，O(n²)"),
    ("counting_sort", "计数排序", "algorithm", "非比较排序，统计每个值出现次数再累加定位，O(n+k)，需额外空间"),
    ("radix_sort", "基数排序", "algorithm", "按位排序，每次稳定排序一位，O(k·n)，需要稳定子排序算法"),
]


# 关系定义：(source_id, target_id, relation_type)
# relation_type: prerequisite(前置), includes(包含), similar(相似), extends(扩展), implemented_by(由...实现)
EDGES = [
    # 章节 → 子节点
    ("ds_intro", "array", "includes"),
    ("ds_intro", "linked_list", "includes"),
    ("ds_intro", "stack", "includes"),
    ("ds_intro", "queue", "includes"),
    ("tree_intro", "binary_tree", "includes"),
    ("tree_intro", "heap", "includes"),
    ("graph_intro", "graph_representation", "includes"),
    ("graph_intro", "dfs", "includes"),
    ("graph_intro", "bfs", "includes"),
    ("graph_intro", "shortest_path", "includes"),
    ("algo_intro", "divide_and_conquer", "includes"),
    ("algo_intro", "dynamic_programming", "includes"),
    ("algo_intro", "greedy", "includes"),
    ("algo_intro", "backtracking", "includes"),
    ("complexity_intro", "time_complexity", "includes"),
    ("complexity_intro", "space_complexity", "includes"),
    ("complexity_intro", "asymptotic_notation", "includes"),
    ("sort_summary", "bubble_sort", "includes"),
    ("sort_summary", "insertion_sort", "includes"),
    ("sort_summary", "selection_sort", "includes"),
    ("sort_summary", "merge_sort", "includes"),
    ("sort_summary", "quick_sort", "includes"),
    ("sort_summary", "heap_sort", "includes"),

    # 前置关系
    ("array", "stack", "implemented_by"),
    ("array", "queue", "implemented_by"),
    ("linked_list", "singly_linked_list", "includes"),
    ("linked_list", "doubly_linked_list", "includes"),
    ("linked_list", "stack", "implemented_by"),
    ("linked_list", "queue", "implemented_by"),

    ("binary_tree", "full_binary_tree", "includes"),
    ("binary_tree", "complete_binary_tree", "includes"),
    ("binary_tree", "binary_search_tree", "extends"),
    ("binary_tree", "binary_tree_traversal", "prerequisite"),
    ("binary_tree_traversal", "preorder", "includes"),
    ("binary_tree_traversal", "inorder", "includes"),
    ("binary_tree_traversal", "postorder", "includes"),
    ("binary_tree_traversal", "level_order", "includes"),

    ("binary_search_tree", "bst_insert", "prerequisite"),
    ("binary_search_tree", "bst_delete", "prerequisite"),
    ("binary_search_tree", "bst_search", "prerequisite"),
    ("binary_search_tree", "avl_tree", "extends"),
    ("binary_search_tree", "red_black_tree", "extends"),

    ("avl_tree", "avl_rotation", "prerequisite"),
    ("red_black_tree", "rotation", "prerequisite"),
    ("red_black_tree", "rbt_insert", "prerequisite"),
    ("red_black_tree", "rbt_delete", "prerequisite"),
    ("avl_rotation", "rotation", "includes"),
    ("rbt_insert", "rbt_delete", "prerequisite"),

    ("complete_binary_tree", "heap", "prerequisite"),
    ("heap", "heapify", "prerequisite"),
    ("heap", "heap_sort", "prerequisite"),

    ("graph_representation", "dfs", "prerequisite"),
    ("graph_representation", "bfs", "prerequisite"),
    ("dfs", "topological_sort", "prerequisite"),
    ("bfs", "shortest_path", "prerequisite"),
    ("shortest_path", "dijkstra", "includes"),
    ("shortest_path", "floyd", "includes"),
    ("dijkstra", "greedy", "prerequisite"),
    ("union_find", "kruskal", "prerequisite"),
    ("union_find", "prim", "prerequisite"),
    ("min_spanning_tree", "kruskal", "includes"),
    ("min_spanning_tree", "prim", "includes"),

    ("divide_and_conquer", "merge_sort", "implemented_by"),
    ("divide_and_conquer", "quick_sort", "implemented_by"),
    ("divide_and_conquer", "binary_search", "implemented_by"),
    ("merge_sort", "quick_sort", "similar"),
    ("quick_sort", "pivot", "prerequisite"),
    ("quick_sort", "partition", "prerequisite"),
    ("merge_sort", "heap_sort", "similar"),

    ("binary_search", "arrays", "prerequisite"),
]


# 为向量库准备的教材片段（人工编写，模拟教材原文）
VECTOR_DOCS = [
    {
        "id": "doc_quick_sort_1",
        "text": "快速排序（Quick Sort）是由 Tony Hoare 于 1959 年提出的分治排序算法。核心思想是：在待排序数组中选择一个'基准值'（pivot），将数组划分为两部分——小于基准值的放左边，大于等于基准值的放右边。然后递归地对左右两部分分别排序。分区过程可以使用 Lomuto 方案或 Hoare 方案实现。",
        "metadata": {"source": "数据结构教材第8章", "chapter": "quick_sort", "page": 215},
    },
    {
        "id": "doc_quick_sort_2",
        "text": "快速排序的时间复杂度：平均 O(n log n)，最坏 O(n²)（当每次选到最大或最小值做 pivot 时）。实际应用中，通过随机化选择 pivot、三数取中等策略可以显著降低最坏情况概率。快速排序是原地排序，空间复杂度 O(log n)（递归栈）。快速排序是不稳定排序——相等元素在排序后相对位置可能改变。",
        "metadata": {"source": "算法导论第7章", "chapter": "quick_sort", "page": 178},
    },
    {
        "id": "doc_merge_sort_1",
        "text": "归并排序（Merge Sort）也是分治思想的体现。步骤：1) 将数组从中间一分为二；2) 递归地对左右两半分别排序；3) 将两个有序数组合并成一个有序数组。合并过程使用双指针：两个指针分别指向两个有序数组的开头，比较后将较小值放入结果数组并推进指针。",
        "metadata": {"source": "数据结构教材第8章", "chapter": "merge_sort", "page": 200},
    },
    {
        "id": "doc_red_black_1",
        "text": "红黑树（Red-Black Tree）是一种自平衡的二叉搜索树，通过五条颜色规则保证了树的高度不会超过 2·log₂(n+1)，确保查找、插入、删除都是 O(log n)。五条规则：1) 每个节点是红色或黑色；2) 根节点是黑色；3) 所有叶子节点（NIL）是黑色；4) 红节点的子节点必须是黑色（不能有连续红节点）；5) 从任意节点到其所有叶子的路径上，黑节点数量相同。",
        "metadata": {"source": "算法导论第13章", "chapter": "red_black_tree", "page": 313},
    },
    {
        "id": "doc_avl_1",
        "text": "AVL 树（Adelson-Velsky and Landis Tree）是最早提出的自平衡二叉搜索树。它的平衡条件比红黑树更严格：任意节点的左右子树高度差（称为平衡因子）的绝对值不超过 1。当插入或删除导致某节点平衡因子超过阈值时，需要通过旋转恢复平衡。AVL 树在查找密集的场景下比红黑树快，但插入删除的旋转次数通常更多。",
        "metadata": {"source": "数据结构教材第6章", "chapter": "avl_tree", "page": 160},
    },
    {
        "id": "doc_graph_dfs_1",
        "text": "深度优先搜索（DFS）和广度优先搜索（BFS）是图遍历的两种基本方式。DFS 沿着一条路尽可能深入，遇到死胡同就回溯。实现上可以用递归（隐式栈）或显式栈。BFS 像水波纹一样一圈一圈扩散，用队列实现。DFS 适合拓扑排序、连通分量检测、回溯问题；BFS 适合无权最短路径、层序遍历问题。",
        "metadata": {"source": "算法导论第22章", "chapter": "graph_traversal", "page": 530},
    },
    {
        "id": "doc_dijkstra_1",
        "text": "Dijkstra 算法用于求单源最短路径。核心是贪心思想：维护一个最小堆（优先队列），每次取出距离起点最近且未确定的顶点，用它的邻接边松弛更新其他顶点的距离。算法要求所有边的权值非负（贪心选择性质的前提）。时间复杂度 O((V+E)log V)（二叉堆）。若有负权但无负环，应用 Bellman-Ford。",
        "metadata": {"source": "算法导论第24章", "chapter": "dijkstra", "page": 658},
    },
    {
        "id": "doc_heap_1",
        "text": "堆（Heap）是一种特殊的完全二叉树，满足堆性质：大顶堆（父节点值 ≥ 子节点值）或小顶堆（父节点值 ≤ 子节点值）。堆可以用数组表示——若父节点索引为 i，则左子节点为 2i+1，右子节点为 2i+2。堆的常用操作：插入（末尾添加 → 上浮）、取堆顶（取出堆顶 → 末尾放堆顶 → 下沉）、堆化（O(n)）。堆常用于优先队列、堆排序、图算法（Dijkstra 的优先队列）。",
        "metadata": {"source": "数据结构教材第5章", "chapter": "heap", "page": 130},
    },
]


async def init_knowledge_base():
    """初始化图谱 + 向量库"""
    g = get_graph()
    v = get_vector()

    # 1. 灌入图谱节点
    for nid, name, cat, desc in NODES:
        if not g.get_node(nid):
            g.add_node(nid, name, category=cat, description=desc)
    for src, tgt, rel in EDGES:
        if g.get_node(src) and g.get_node(tgt):
            g.add_edge(src, tgt, relation=rel)
    g.save()
    logger.info(f"✅ 图谱初始化完成: {g.get_stats()}")

    # 2. 灌入向量文档
    existing = v.count()
    if existing == 0:
        await v.add_documents(VECTOR_DOCS)
        logger.info(f"✅ 向量库初始化完成: {v.count()} 条文档")
    else:
        logger.info(f"📚 向量库已有 {existing} 条文档，跳过初始化")


if __name__ == "__main__":
    asyncio.run(init_knowledge_base())
