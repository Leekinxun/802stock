"""
HTTP客户端封装
提供统一的HTTP请求功能,支持重试、超时、代理等
"""
import time
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.legacy.utils.logger import get_logger

logger = get_logger(__name__)


class HTTPClient:
    """HTTP客户端封装类"""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 1,
        headers: Optional[Dict[str, str]] = None,
        proxies: Optional[Dict[str, str]] = None
    ):
        """
        初始化HTTP客户端

        Args:
            timeout: 请求超时时间(秒)
            max_retries: 最大重试次数
            retry_delay: 重试延迟(秒)
            headers: 默认请求头
            proxies: 代理配置
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.default_headers = headers or {}
        self.proxies = proxies

        # 创建session
        self.session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 设置默认请求头
        self.session.headers.update(self.default_headers)

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> requests.Response:
        """
        发送GET请求

        Args:
            url: 请求URL
            params: 查询参数
            headers: 请求头
            timeout: 超时时间
            **kwargs: 其他requests参数

        Returns:
            响应对象
        """
        return self._request('GET', url, params=params, headers=headers, timeout=timeout, **kwargs)

    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> requests.Response:
        """
        发送POST请求

        Args:
            url: 请求URL
            data: 表单数据
            json: JSON数据
            headers: 请求头
            timeout: 超时时间
            **kwargs: 其他requests参数

        Returns:
            响应对象
        """
        return self._request('POST', url, data=data, json=json, headers=headers, timeout=timeout, **kwargs)

    def _request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """
        发送HTTP请求(内部方法)

        Args:
            method: 请求方法
            url: 请求URL
            **kwargs: requests参数

        Returns:
            响应对象

        Raises:
            requests.RequestException: 请求失败
        """
        timeout = kwargs.pop('timeout', self.timeout)
        headers = kwargs.pop('headers', None) or {}

        # 合并请求头
        merged_headers = {**self.default_headers, **headers}

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"请求 {method} {url} (尝试 {attempt + 1}/{self.max_retries + 1})")

                response = self.session.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    timeout=timeout,
                    proxies=self.proxies,
                    **kwargs
                )

                response.raise_for_status()
                logger.debug(f"请求成功: {method} {url} - 状态码 {response.status_code}")
                return response

            except requests.RequestException as e:
                logger.warning(f"请求失败: {method} {url} - {str(e)}")

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"请求最终失败: {method} {url}")
                    raise

        raise requests.RequestException(f"请求失败: {method} {url}")

    def close(self):
        """关闭session"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
