# 在现有的导入部分添加
import os
from decimal import Decimal
from django.db import transaction

# views.py
import time
from datetime import datetime

from django.http import FileResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
import hashlib
from .models import Attachment, Application
from .serializers import (ApplicationCreateSerializer,
                          ApplicationListResponseSerializer,
                          ApplicationChangeReviewSerializer, ApplicationRevokeReviewSerializer,
                          SimpleFileUploadSerializer,
                          SafeTeacherPendingApplicationListSerializer, TeacherReReviewSerializer)
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from user.models import User
from score.models import AcademicPerformance

from rest_framework.decorators import api_view, permission_classes

from django.core.paginator import Paginator
from django.db.models import Q


class SimpleFileUploadView(APIView):
    """
    简化文件上传接口 - 允许重复上传相同文件
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        """
        文件上传接口 - 允许重复上传版本
        """
        try:
            print("=== 文件上传请求开始 ===")
            print("请求方法:", request.method)
            print("请求内容类型:", request.content_type)
            print("请求FILES keys:", list(request.FILES.keys()))

            # 🎯 修复：动态获取文件字段名
            uploaded_file = None
            file_field_name = None

            for field_name, file_obj in request.FILES.items():
                print(f"找到文件字段: {field_name} -> {file_obj.name}")
                uploaded_file = file_obj
                file_field_name = field_name
                break

            if not uploaded_file:
                print("❌ 没有找到任何文件字段")
                return Response({
                    'success': False,
                    'message': '请选择要上传的文件',
                    'debug': {
                        'available_file_fields': list(request.FILES.keys()),
                        'available_data_fields': list(request.data.keys())
                    },
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"✅ 使用文件字段: {file_field_name}")
            print(f"文件名: {uploaded_file.name}")
            print(f"文件大小: {uploaded_file.size}")

            # 验证文件类型
            allowed_extensions = ['jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx']
            file_extension = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''
            print("文件扩展名:", file_extension)

            if file_extension not in allowed_extensions:
                print(f"❌ 不支持的文件类型: {file_extension}")
                return Response({
                    'success': False,
                    'message': f'不支持的文件类型。支持的类型: {", ".join(allowed_extensions)}',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 验证文件大小（限制为10MB）
            max_size = 100 * 1024 * 1024  # 10MB
            print(f"文件大小: {uploaded_file.size} bytes, 限制: {max_size} bytes")

            if uploaded_file.size > max_size:
                print("❌ 文件大小超过限制")
                return Response({
                    'success': False,
                    'message': '文件大小不能超过10MB',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 🎯 修改点1：移除哈希去重检查，改为计算哈希用于记录
            print("开始计算文件哈希...")
            file_hash = self.calculate_file_hash(uploaded_file)
            print("文件哈希:", file_hash)

            # 🎯 修改点2：检查是否已存在相同文件，如果存在则更新记录
            existing_attachment = Attachment.objects.filter(file_hash=file_hash).first()

            if existing_attachment:
                print("⚠️ 文件已存在，更新现有文件记录")
                # 可以选择删除旧文件或保留（这里选择更新记录）
                try:
                    # 更新现有记录的文件信息
                    existing_attachment.file = uploaded_file
                    existing_attachment.name = uploaded_file.name
                    existing_attachment.file_size = uploaded_file.size
                    existing_attachment.save()

                    print("✅ 文件记录更新成功")
                    response_data = {
                        'success': True,
                        'message': '文件已存在，记录已更新',
                        'data': {
                            'id': str(existing_attachment.id),
                            'name': existing_attachment.name,
                            'file_url': existing_attachment.file.url if existing_attachment.file else None,
                            'file_hash': existing_attachment.file_hash,
                            'file_size': existing_attachment.file_size,
                            'uploaded_at': existing_attachment.uploaded_at.isoformat() if existing_attachment.uploaded_at else None,
                            'hash_algorithm': 'SHA-256',
                            'action': 'updated_existing'  # 标识是更新操作
                        }
                    }
                    return Response(response_data, status=status.HTTP_200_OK)

                except Exception as update_error:
                    print(f"❌ 文件更新失败: {str(update_error)}")
                    import traceback
                    print(f"更新错误堆栈: {traceback.format_exc()}")
                    # 如果更新失败，继续创建新记录

            # 准备数据 - 使用正确的字段名
            upload_data = {
                'file': uploaded_file
            }
            print("准备上传数据:", upload_data)

            # 使用简化序列化器创建附件
            print("开始序列化器验证...")
            serializer = SimpleFileUploadSerializer(data=upload_data)

            if serializer.is_valid():
                print("✅ 序列化器验证通过")
                print("验证数据:", serializer.validated_data)

                try:
                    attachment = serializer.save()
                    print("✅ 文件保存成功")
                    print("附件ID:", attachment.id)
                    print("附件名称:", attachment.name)

                    # 返回成功响应
                    response_data = {
                        'success': True,
                        'message': '文件上传成功',
                        'data': {
                            'id': str(attachment.id),
                            'name': attachment.name,
                            'file_url': attachment.file.url if attachment.file else None,
                            'file_hash': attachment.file_hash,
                            'file_size': attachment.file_size,
                            'uploaded_at': attachment.uploaded_at.isoformat() if attachment.uploaded_at else None,
                            'hash_algorithm': 'SHA-256',
                            'action': 'created_new'  # 标识是新建操作
                        }
                    }

                    print("✅ 文件上传完成，返回响应")
                    return Response(response_data, status=status.HTTP_200_OK)

                except Exception as save_error:
                    print(f"❌ 文件保存失败: {str(save_error)}")
                    import traceback
                    print(f"保存错误堆栈: {traceback.format_exc()}")
                    return Response({
                        'success': False,
                        'message': f'文件保存失败: {str(save_error)}',
                        'data': None
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                print("❌ 序列化器验证失败")
                print("验证错误:", serializer.errors)
                return Response({
                    'success': False,
                    'message': '文件数据验证失败',
                    'errors': serializer.errors,
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"❌ 文件上传过程异常: {str(e)}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'上传过程中发生错误: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def calculate_file_hash(self, file):
        """计算文件的SHA-256哈希值"""
        hash_sha256 = hashlib.sha256()

        # 重置文件指针到开头
        if hasattr(file, 'seek'):
            file.seek(0)

        # 分块读取文件计算哈希
        for chunk in file.chunks(chunk_size=8192):
            hash_sha256.update(chunk)

        # 再次重置文件指针
        if hasattr(file, 'seek'):
            file.seek(0)

        return hash_sha256.hexdigest()


class FileDownloadByHashView(APIView):
    """
    文件下载接口 - 基于文件哈希值
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        通过文件哈希值下载文件
        GET /api/attachments/download/?file_hash=<file_hash>
        """
        try:
            print("=== 文件下载请求开始 ===")
            print("请求用户:", request.user.school_id)
            print("请求参数:", dict(request.query_params))

            # 获取文件哈希参数
            file_hash = request.query_params.get('id')
            if not file_hash:
                return Response({
                    "success": False,
                    "message": "请提供文件哈希参数",
                    "data": None
                }, status=400)

            # 清理哈希值（移除空格，转为小写）
            file_hash = file_hash.strip().lower()
            print(f"清理后的文件哈希: {file_hash}")

            # 验证哈希格式
            if not self.is_valid_hash(file_hash):
                return Response({
                    "success": False,
                    "message": "文件哈希格式不正确",
                    "data": None
                }, status=400)

            # 查找附件
            try:
                attachment = Attachment.objects.get(file_hash=file_hash)
                print(f"找到附件: {attachment.name} (ID: {attachment.id})")
            except Attachment.DoesNotExist:
                print(f"❌ 未找到哈希为 {file_hash} 的附件")
                return Response({
                    "success": False,
                    "message": "文件不存在",
                    "data": None
                }, status=404)
            except Exception as e:
                print(f"查找附件异常: {e}")
                return Response({
                    "success": False,
                    "message": "文件查找失败",
                    "data": None
                }, status=500)

            # 检查文件是否存在
            if not attachment.file:
                print("❌ 附件文件字段为空")
                return Response({
                    "success": False,
                    "message": "文件数据丢失",
                    "data": None
                }, status=404)

            # 检查物理文件是否存在
            try:
                file_path = attachment.file.path
                if not os.path.exists(file_path):
                    print(f"❌ 物理文件不存在: {file_path}")
                    return Response({
                        "success": False,
                        "message": "文件已被删除或移动",
                        "data": None
                    }, status=404)
            except Exception as e:
                print(f"检查物理文件异常: {e}")
                # 如果无法获取本地路径，尝试通过URL访问

            # 🎯 权限检查：用户只能下载自己申请的附件
            if not self.check_download_permission(request.user, attachment):
                print(f"❌ 用户无权限下载此文件: {request.user.school_id}")
                return Response({
                    "success": False,
                    "message": "无权访问此文件",
                    "data": None
                }, status=403)

            # 准备文件响应
            try:
                print(f"准备下载文件: {attachment.name}")
                print(f"文件大小: {attachment.file_size} bytes")
                print(f"文件路径: {attachment.file.name}")

                # 获取文件对象
                file_obj = attachment.file
                file_obj.open('rb')  # 以二进制模式打开文件

                # 创建文件响应
                response = FileResponse(
                    file_obj,
                    content_type='application/octet-stream',  # 通用二进制类型
                    as_attachment=True,  # 作为附件下载
                    filename=attachment.name  # 下载时的文件名
                )

                # 设置响应头
                response['Content-Length'] = attachment.file_size or file_obj.size
                response['Content-Disposition'] = f'attachment; filename="{self.safe_filename(attachment.name)}"'
                response['X-File-Hash'] = attachment.file_hash
                response['X-File-Name'] = self.safe_filename(attachment.name)

                print("✅ 文件响应准备完成")
                return response

            except Exception as e:
                print(f"❌ 文件响应创建失败: {e}")
                return Response({
                    "success": False,
                    "message": f"文件访问失败: {str(e)}",
                    "data": None
                }, status=500)

        except Exception as e:
            print(f"❌ 文件下载过程异常: {str(e)}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            return Response({
                "success": False,
                "message": f"下载过程中发生错误: {str(e)}",
                "data": None
            }, status=500)

    def check_download_permission(self, user, attachment):
        """
        检查用户是否有权限下载此文件
        规则：用户只能下载自己申请的附件
        """
        try:
            # 方法1：通过申请关联检查
            if hasattr(attachment, 'application_set'):
                # 查找与此附件关联的申请
                related_applications = attachment.application_set.filter(user=user)
                if related_applications.exists():
                    print(f"✅ 权限验证通过: 用户 {user.school_id} 拥有此文件的使用权")
                    return True

            # 方法2：通过多对多关系检查
            if hasattr(attachment, 'applications'):
                related_applications = attachment.applications.filter(user=user)
                if related_applications.exists():
                    print(f"✅ 权限验证通过: 用户 {user.school_id} 拥有此文件的使用权")
                    return True

            # 方法3：如果是老师或管理员，可能有更广泛的权限
            if user.user_type in [1, 2]:  # 老师或管理员
                print(f"✅ 权限验证通过: 用户 {user.school_id} 是老师或管理员")
                return True

            print(f"❌ 权限验证失败: 用户 {user.school_id} 无权访问此文件")
            return False

        except Exception as e:
            print(f"权限检查异常: {e}")
            return False

    def is_valid_hash(self, hash_string):
        """
        验证是否为有效的文件哈希格式
        """
        if not isinstance(hash_string, str):
            return False

        clean_hash = hash_string.strip()

        # SHA-256哈希应该是64个字符的十六进制字符串
        if len(clean_hash) == 64:
            try:
                int(clean_hash, 16)  # 验证是否为有效的十六进制
                return True
            except ValueError:
                return False

        # 也支持较短的哈希（如MD5等）
        elif len(clean_hash) in [32, 40]:  # MD5或SHA-1
            try:
                int(clean_hash, 16)
                return True
            except ValueError:
                return False

        return False

    def safe_filename(self, filename):
        """
        安全处理文件名，防止中文乱码和特殊字符问题
        """
        try:
            # 处理中文文件名
            import urllib.parse
            safe_name = urllib.parse.quote(filename)
            return safe_name
        except:
            # 如果处理失败，返回原始文件名
            return filename


class FileDownloadInfoView(APIView):
    """
    文件信息查询接口 - 基于文件哈希值
    用于在下载前获取文件信息
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        获取文件信息（不下载）
        GET /api/attachments/info/?file_hash=<file_hash>
        """
        try:
            print("=== 文件信息查询请求开始 ===")
            file_hash = request.query_params.get('file_hash')
            if not file_hash:
                return Response({
                    "success": False,
                    "message": "请提供文件哈希参数",
                    "data": None
                }, status=400)

            # 清理哈希值
            file_hash = file_hash.strip().lower()

            # 查找附件
            try:
                attachment = Attachment.objects.get(file_hash=file_hash)
            except Attachment.DoesNotExist:
                return Response({
                    "success": False,
                    "message": "文件不存在",
                    "data": None
                }, status=404)

            # 权限检查
            if not self.check_download_permission(request.user, attachment):
                return Response({
                    "success": False,
                    "message": "无权访问此文件",
                    "data": None
                }, status=403)

            # 返回文件信息
            file_info = {
                "id": str(attachment.id),
                "name": attachment.name,
                "file_hash": attachment.file_hash,
                "file_size": attachment.file_size,
                "file_url": attachment.file.url if attachment.file else None,
                "uploaded_at": attachment.uploaded_at.isoformat() if attachment.uploaded_at else None,
                "can_download": True
            }

            return Response({
                "success": True,
                "message": "文件信息获取成功",
                "data": file_info
            })

        except Exception as e:
            print(f"文件信息查询异常: {e}")
            return Response({
                "success": False,
                "message": f"文件信息查询失败: {str(e)}",
                "data": None
            }, status=500)

    def check_download_permission(self, user, attachment):
        """检查下载权限（复用上面的方法）"""
        # 这里可以复用 FileDownloadByHashView 的权限检查逻辑
        # 或者根据需要进行调整
        return True  # 简化版本，实际使用时需要实现完整的权限检查


class FileDeleteView(APIView):
    """
    文件删除接口 - 基于文件哈希和上传时间
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        """
        删除文件
        DELETE /api/attachments/delete/
        请求参数:
        - id: string (文件SHA-256哈希) - 必需
        - UploadTime: number (对应申请的上传时间，为0表示无对应申请) - 必需
        """
        try:
            print("=== 文件删除请求开始 ===")
            print("请求用户:", request.user.school_id)
            print("请求方法:", request.method)
            print("请求数据:", dict(request.data))

            # 获取请求参数
            file_hash = request.data.get('id')  # 文件SHA-256哈希
            upload_time = request.data.get('UploadTime')  # 对应申请的上传时间

            # 参数验证
            if not file_hash:
                return Response({
                    "success": False,
                    "message": "请提供文件哈希参数(id)",
                    "data": None
                }, status=400)

            if upload_time is None:
                return Response({
                    "success": False,
                    "message": "请提供UploadTime参数",
                    "data": None
                }, status=400)

            # 清理和验证文件哈希
            file_hash = file_hash.strip().lower()
            if not self.is_valid_sha256_hash(file_hash):
                return Response({
                    "success": False,
                    "message": "文件哈希格式不正确，应为64位SHA-256哈希",
                    "data": None
                }, status=400)

            # 处理UploadTime参数
            try:
                upload_time = int(upload_time)
            except (ValueError, TypeError):
                return Response({
                    "success": False,
                    "message": "UploadTime参数格式错误，应为数字",
                    "data": None
                }, status=400)

            print(f"清理后的参数 - 文件哈希: {file_hash}, UploadTime: {upload_time}")

            # 查找附件
            try:
                attachment = Attachment.objects.get(file_hash=file_hash)
                print(f"找到附件: {attachment.name} (ID: {attachment.id})")
            except Attachment.DoesNotExist:
                print(f"❌ 未找到哈希为 {file_hash} 的附件")
                return Response({
                    "success": False,
                    "message": "文件不存在",
                    "data": None
                }, status=404)

            # 🎯 权限检查
            if not self.check_delete_permission(request.user, attachment, upload_time):
                print(f"❌ 用户无权限删除此文件: {request.user.school_id}")
                return Response({
                    "success": False,
                    "message": "无权删除此文件",
                    "data": None
                }, status=403)

            # 🎯 业务逻辑：根据UploadTime处理不同的删除场景
            delete_result = self.handle_delete_operation(request.user, attachment, upload_time)

            if not delete_result['success']:
                return Response({
                    "success": False,
                    "message": delete_result['message'],
                    "data": None
                }, status=delete_result.get('status', 400))

            # 返回成功响应
            response_data = {
                "success": True,
                "message": delete_result['message'],
                "data": {
                    "deleted_file_hash": file_hash,
                    "deleted_file_name": attachment.name,
                    "operation_type": delete_result['operation_type'],
                    "remaining_references": delete_result.get('remaining_references', 0)
                }
            }

            print(f"✅ 文件删除操作完成: {delete_result['message']}")
            return Response(response_data, status=200)

        except Exception as e:
            print(f"❌ 文件删除过程异常: {str(e)}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")
            return Response({
                "success": False,
                "message": f"删除过程中发生错误: {str(e)}",
                "data": None
            }, status=500)

    def handle_delete_operation(self, user, attachment, upload_time):
        """
        处理删除操作的核心逻辑
        根据UploadTime的值执行不同的删除策略
        """
        try:
            # 场景1: UploadTime = 0 - 完全删除文件（无对应申请）
            if upload_time == 0:
                return self.delete_file_completely(attachment)

            # 场景2: UploadTime > 0 - 从特定申请中移除附件关联
            else:
                return self.remove_file_from_application(user, attachment, upload_time)

        except Exception as e:
            print(f"删除操作处理异常: {e}")
            return {
                "success": False,
                "message": f"删除操作失败: {str(e)}"
            }

    def delete_file_completely(self, attachment):
        """
        场景1: 完全删除文件（UploadTime = 0）
        - 删除物理文件
        - 删除数据库记录
        - 检查是否有其他引用
        """
        try:
            print("=== 执行完全删除操作 ===")

            # 检查文件是否被其他申请引用
            reference_count = self.get_file_reference_count(attachment)
            print(f"文件被 {reference_count} 个申请引用")

            if reference_count > 0:
                return {
                    "success": False,
                    "message": f"文件正在被 {reference_count} 个申请使用，无法完全删除",
                    "operation_type": "blocked_complete_delete",
                    "remaining_references": reference_count
                }

            # 记录文件信息用于响应
            file_info = {
                "file_hash": attachment.file_hash,
                "file_name": attachment.name,
                "file_size": attachment.file_size
            }

            # 删除物理文件
            physical_deleted = self.delete_physical_file(attachment)

            # 删除数据库记录
            attachment_id = attachment.id
            attachment.delete()

            print(f"✅ 文件完全删除成功: {file_info['file_name']}")

            return {
                "success": True,
                "message": "文件已完全删除",
                "operation_type": "complete_delete",
                "file_info": file_info,
                "physical_deleted": physical_deleted
            }

        except Exception as e:
            print(f"完全删除操作异常: {e}")
            return {
                "success": False,
                "message": f"完全删除失败: {str(e)}"
            }

    def remove_file_from_application(self, user, attachment, upload_time):
        """
        场景2: 从特定申请中移除附件关联（UploadTime > 0）
        - 只移除关联关系，不删除物理文件
        - 检查申请是否存在且属于当前用户
        """
        try:
            print("=== 执行从申请中移除附件操作 ===")
            print(f"目标UploadTime: {upload_time}")

            # 查找对应的申请
            application = self.find_application_by_upload_time(user, upload_time)
            if not application:
                return {
                    "success": False,
                    "message": "未找到对应的申请记录",
                    "status": 404
                }

            # 检查申请是否包含此附件
            if not application.Attachments.filter(file_hash=attachment.file_hash).exists():
                return {
                    "success": False,
                    "message": "该申请中未找到此附件",
                    "status": 404
                }

            # 从申请中移除附件
            application.Attachments.remove(attachment)
            print(f"✅ 从申请中移除附件成功: {attachment.name}")

            # 更新attachments_array字段（如果存在）
            if hasattr(application, 'attachments_array') and application.attachments_array:
                application.attachments_array = [
                    item for item in application.attachments_array
                    if item.get('file_hash') != attachment.file_hash
                ]
                application.save()
                print("attachments_array字段已更新")

            # 检查文件的剩余引用
            remaining_references = self.get_file_reference_count(attachment)
            print(f"文件剩余引用数: {remaining_references}")

            return {
                "success": True,
                "message": "已从申请中移除附件",
                "operation_type": "remove_from_application",
                "remaining_references": remaining_references,
                "application_title": application.Title
            }

        except Exception as e:
            print(f"移除附件操作异常: {e}")
            return {
                "success": False,
                "message": f"移除附件失败: {str(e)}"
            }

    def find_application_by_upload_time(self, user, upload_time):
        """
        根据UploadTime查找申请记录
        """
        try:
            print(f"查找申请 - 用户: {user.school_id}, UploadTime: {upload_time}")

            # 精确查找
            try:
                application = Application.objects.get(UploadTime=upload_time, user=user)
                print(f"通过UploadTime找到申请: {application.Title}")
                return application
            except Application.DoesNotExist:
                print("精确查找失败，尝试范围查找")

                # 范围查找（前后5秒）
                time_range_start = upload_time - 5000
                time_range_end = upload_time + 5000

                applications = Application.objects.filter(
                    user=user,
                    UploadTime__range=(time_range_start, time_range_end)
                ).order_by('-UploadTime')

                if applications.exists():
                    application = applications.first()
                    print(f"通过范围查找找到申请: {application.Title}")
                    return application
                else:
                    print("通过UploadTime未找到申请")
                    return None

        except Exception as e:
            print(f"查找申请异常: {e}")
            return None

    def get_file_reference_count(self, attachment):
        """
        获取文件被引用的次数
        """
        try:
            # 方法1: 通过多对多关系统计
            if hasattr(attachment, 'applications'):
                return attachment.applications.count()

            # 方法2: 通过反向关系统计
            if hasattr(attachment, 'application_set'):
                return attachment.application_set.count()

            # 方法3: 通用统计方法
            from django.db.models import Q
            return Application.objects.filter(Attachments=attachment).count()

        except Exception as e:
            print(f"统计文件引用次数异常: {e}")
            return 0

    def delete_physical_file(self, attachment):
        """
        删除物理文件
        """
        try:
            if attachment.file and hasattr(attachment.file, 'path'):
                import os
                file_path = attachment.file.path
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"✅ 物理文件删除成功: {file_path}")
                    return True
                else:
                    print(f"⚠️ 物理文件不存在: {file_path}")
                    return False
            else:
                print("⚠️ 无物理文件路径")
                return False
        except Exception as e:
            print(f"❌ 物理文件删除失败: {e}")
            return False

    def check_delete_permission(self, user, attachment, upload_time):
        """
        检查删除权限
        """
        try:
            # 场景1: UploadTime = 0 - 需要完全删除权限
            if upload_time == 0:
                # 只有文件的所有者或管理员可以完全删除
                reference_count = self.get_file_reference_count(attachment)
                if reference_count == 0:
                    # 无引用的文件，创建者或管理员可以删除
                    return user.user_type in [1, 2]  # 老师或管理员
                else:
                    # 有引用的文件，需要管理员权限
                    return user.user_type == 2  # 仅管理员

            # 场景2: UploadTime > 0 - 检查申请所有权
            else:
                application = self.find_application_by_upload_time(user, upload_time)
                if application and application.user == user:
                    return True
                return False

        except Exception as e:
            print(f"权限检查异常: {e}")
            return False

    def is_valid_sha256_hash(self, hash_string):
        """
        验证是否为有效的SHA-256哈希
        """
        if not isinstance(hash_string, str):
            return False

        clean_hash = hash_string.strip()

        # SHA-256哈希应该是64个字符的十六进制字符串
        if len(clean_hash) == 64:
            try:
                int(clean_hash, 16)
                return True
            except ValueError:
                return False

        return False


class ApplicationCreateView(APIView):
    """
    创建申请接口 - 修复版本
    """
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        """检查用户权限"""
        super().check_permissions(request)

        # 检查用户类型，只有学生可以创建申请
        if not request.user.is_student:
            self.permission_denied(
                request,
                message="只有学生用户可以创建申请"
            )

    def post(self, request):
        """
        创建新的申请 - 支持 attachments_array
        """
        try:
            print("=== 创建申请请求数据 ===")
            print("请求数据:", request.data)

            # 转换字段名以匹配序列化器
            transformed_data = self.transform_request_data(request.data)
            print("转换后数据:", transformed_data)

            with transaction.atomic():
                # 🎯 提前提取附件ID和数组
                attachment_ids = []
                attachments_array = transformed_data.get('attachments_array', [])

                if 'Attachments' in transformed_data:
                    attachments_data = transformed_data.pop('Attachments')
                    print("提取的附件数据:", attachments_data)

                    # 处理附件数据格式
                    if isinstance(attachments_data, list):
                        for item in attachments_data:
                            if isinstance(item, dict):
                                attachment_id = item.get('id')
                                if attachment_id:
                                    attachment_ids.append(attachment_id)
                            elif isinstance(item, str):
                                attachment_ids.append(item)
                    print("处理后的附件ID列表:", attachment_ids)

                # 🎯 确保 attachments_array 在数据中
                if 'attachments_array' not in transformed_data:
                    transformed_data['attachments_array'] = attachments_array

                print("最终序列化数据:", transformed_data)

                # 验证请求数据
                serializer = ApplicationCreateSerializer(data=transformed_data)

                if not serializer.is_valid():
                    print("=== 序列化器验证错误 ===")
                    print("错误详情:", serializer.errors)
                    return Response({
                        'success': False,
                        'message': '数据验证失败',
                        'errors': serializer.errors,
                        'data': None
                    }, status=status.HTTP_400_BAD_REQUEST)

                print("=== 序列化器验证通过 ===")
                print("验证数据:", serializer.validated_data)

                # 🎯 创建申请记录 - 包含 attachments_array
                application = Application.objects.create(
                    user=request.user,
                    Type=serializer.validated_data['Type'],
                    Title=serializer.validated_data['Title'],
                    ApplyScore=serializer.validated_data['ApplyScore'],
                    Description=serializer.validated_data.get('Description', ''),
                    Feedback=serializer.validated_data.get('Feedback', ''),
                    extra_data=serializer.validated_data.get('extra_data', {}),
                    attachments_array=serializer.validated_data.get('attachments_array', []),  # 🎯 新增
                    review_status=0,
                    Real_Score=0,
                )

                print("=== 申请创建成功 ===")
                print("申请ID:", application.id)
                print("申请标题:", application.Title)
                print("附件数组:", application.attachments_array)

                # 🎯 处理附件关联（ManyToMany关系）
                if attachment_ids:
                    print("=== 处理附件关联 ===")
                    print("附件哈希列表:", attachment_ids)

                    found_attachments = []
                    for file_hash in attachment_ids:
                        # 🎯 修复：统一转换为小写进行查找
                        normalized_hash = file_hash.lower()
                        print(f"原始哈希: {file_hash} -> 标准化: {normalized_hash}")

                        # 🎯 使用标准化的小写哈希查找
                        attachment = Attachment.objects.filter(file_hash=normalized_hash).first()
                        if attachment:
                            found_attachments.append(attachment)
                            print(f"✅ 找到附件: {attachment.name} (文件哈希: {attachment.file_hash})")
                        else:
                            print(f"⚠️ 附件未找到，标准化哈希: {normalized_hash}")

                    if found_attachments:
                        application.Attachments.set(found_attachments)
                        print(f"✅ 成功关联 {len(found_attachments)} 个附件")

                        # 🎯 同步 attachments_array (保持原始大小写)
                        current_hashes = [att.file_hash for att in found_attachments]
                        application.attachments_array = current_hashes
                        application.save(update_fields=['attachments_array'])
                        print(f"✅ 更新附件数组: {current_hashes}")
                    else:
                        print("⚠️ 没有找到有效的附件")

                # 返回创建成功的响应
                response_serializer = ApplicationListResponseSerializer(application)

                return Response({
                    'success': True,
                    'message': '申请创建成功',
                    'data': response_serializer.data
                }, status=status.HTTP_200_OK)

        except Exception as e:
            print("=== 创建申请异常 ===")
            print("异常信息:", str(e))
            import traceback
            print("堆栈跟踪:", traceback.format_exc())

            return Response({
                'success': False,
                'message': f'创建申请失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # views.py - 修改 transform_request_data 方法
    def transform_request_data(self, request_data):
        """转换前端字段名为后端字段名"""
        transformed = request_data.copy()

        print("=== 字段转换过程 ===")
        print("原始数据:", transformed)

        # 字段名映射：前端 FeedBack → 后端 Feedback
        if 'FeedBack' in transformed:
            transformed['Feedback'] = transformed.pop('FeedBack')
            print("FeedBack → Feedback:", transformed.get('Feedback'))

        # 处理extra_data
        if 'extra_data' in transformed:
            extra_data_value = transformed['extra_data']
            print("extra_data原始值:", extra_data_value, "类型:", type(extra_data_value))

            if isinstance(extra_data_value, str):
                try:
                    import json
                    transformed['extra_data'] = json.loads(extra_data_value)
                    print("extra_data转换成功:", transformed['extra_data'])
                except json.JSONDecodeError:
                    transformed['extra_data'] = {}
            elif isinstance(extra_data_value, dict):
                print("extra_data已经是字典")
            else:
                transformed['extra_data'] = {}

        # 🎯 处理附件数据格式 - 同时设置 attachments_array
        if 'Attachments' in transformed:
            attachments_data = transformed['Attachments']
            print("原始附件数据:", attachments_data)

            attachment_ids = []
            attachment_hashes = []  # 🎯 新增：收集附件哈希

            if isinstance(attachments_data, list):
                for item in attachments_data:
                    print(f"处理附件项: {item}, 类型: {type(item)}")
                    if isinstance(item, dict):
                        attachment_id = item.get('id')
                        if attachment_id:
                            attachment_ids.append(str(attachment_id))
                            attachment_hashes.append(attachment_id)  # 🎯 收集哈希
                            print(f"✅ 从字典提取附件ID: {attachment_id}")
                    elif isinstance(item, str):
                        attachment_ids.append(item)
                        attachment_hashes.append(item)  # 🎯 收集哈希
                        print(f"✅ 使用字符串附件ID: {item}")
                    else:
                        print(f"❌ 忽略无效的附件格式: {item}")

                transformed['Attachments'] = attachment_ids
                # 🎯 新增：设置 attachments_array
                transformed['attachments_array'] = attachment_hashes
                print("🎯 转换后的附件ID列表:", attachment_ids)
                print("🎯 设置的附件数组:", attachment_hashes)
            else:
                print(f"❌ 附件数据不是列表")
                transformed['Attachments'] = []
                transformed['attachments_array'] = []  # 🎯 设置空数组

        # 确保Feedback有值
        if 'Feedback' not in transformed or transformed['Feedback'] is None:
            transformed['Feedback'] = ''
            print("设置Feedback默认值: ''")

        # 🎯 确保 attachments_array 有值（如果没有附件）
        if 'attachments_array' not in transformed:
            transformed['attachments_array'] = []
            print("设置attachments_array默认值: []")

        # 移除不需要的字段
        read_only_fields = ['RealScore', 'ReviewStatus', 'UploadTime', 'ModifyTime']
        for field in read_only_fields:
            if field in transformed:
                print(f"移除只读字段: {field}")
                transformed.pop(field)

        print("最终转换数据:", transformed)
        return transformed


# views.py - 修复ApplicationListView
class ApplicationListView(APIView):
    """
    获取用户申请列表 - 修复版本
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        获取当前用户的所有申请 - 安全版本
        """
        try:
            print("=== 申请列表请求开始 ===")
            print(f"用户: {request.user.school_id}")

            # 获取当前用户的所有申请，按上传时间倒序排列
            applications = Application.objects.filter(user=request.user).order_by('-UploadTime')

            print(f"数据库查询完成，找到 {applications.count()} 条申请")

            # 使用修复后的序列化器
            serializer = ApplicationListResponseSerializer(applications, many=True)

            print("序列化完成")

            # 构建符合前端要求的响应格式
            response_data = {
                "ApplyList": serializer.data
            }

            print("返回响应数据")
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"申请列表错误: {str(e)}")
            import traceback
            print(f"错误堆栈: {traceback.format_exc()}")

            # 返回空列表而不是错误，避免前端崩溃
            return Response({
                "ApplyList": []
            }, status=status.HTTP_200_OK)


class ApplicationDetailByQueryView(APIView):
    """
    申请详情接口 - 使用查询参数
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        获取申请详情 - 通过查询参数
        GET /api/applications/detail/?application_id={application_id}
        """
        try:
            application_id = request.GET.get('application_id') or request.GET.get('pk')

            if not application_id:
                return Response({
                    "success": False,
                    "message": "请提供申请ID参数",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                application = Application.objects.get(id=application_id)
            except Application.DoesNotExist:
                return Response({
                    "success": False,
                    "message": "申请不存在",
                    "data": None
                }, status=status.HTTP_404_NOT_FOUND)
            except ValueError:
                return Response({
                    "success": False,
                    "message": "申请ID格式错误",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 权限验证
            if application.user != request.user and not request.user.is_teacher and not request.user.is_admin:
                return Response({
                    "success": False,
                    "message": "无权查看此申请",
                    "data": None
                }, status=status.HTTP_403_FORBIDDEN)

            # 使用响应序列化器
            serializer = ApplicationListResponseSerializer(application)

            response_data = {
                "success": True,
                "message": "获取申请详情成功",
                "data": serializer.data
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "success": False,
                "message": f"获取申请详情失败: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplicationDeleteView(APIView):
    """
    撤回申请接口 - 修复时间戳问题
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        """
        撤回申请
        DELETE /api/student/material/applications/destroy/
        """
        try:
            # 初始化参数
            application_id = None
            upload_time = None

            # 方式1：从查询参数获取（GET参数）
            if request.GET:
                application_id = request.GET.get('id')
                upload_time = request.GET.get('UploadTime')
                print(f"从查询参数获取 - ID: {application_id}, UploadTime: {upload_time}")

            # 方式2：从请求体获取（JSON格式）
            if not application_id and not upload_time and request.body:
                try:
                    import json
                    body_data = json.loads(request.body)
                    application_id = body_data.get('id')
                    upload_time = body_data.get('UploadTime')
                    print(f"从请求体获取 - ID: {application_id}, UploadTime: {upload_time}")
                except json.JSONDecodeError:
                    print("请求体不是有效的JSON格式")

            # 方式3：对于form-data格式的DELETE请求
            if not application_id and not upload_time and request.POST:
                application_id = request.POST.get('id')
                upload_time = request.POST.get('UploadTime')
                print(f"从POST数据获取 - ID: {application_id}, UploadTime: {upload_time}")

            print(f"最终参数 - ID: {application_id}, UploadTime: {upload_time}")

            if not application_id and not upload_time:
                return Response({
                    "success": False,
                    "message": "请提供申请ID或UploadTime参数",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 查找申请
            application = self.find_application_safe(request.user, application_id, upload_time)
            if not application:
                return Response({
                    "success": False,
                    "message": "未找到对应的申请材料",
                    "data": None
                }, status=status.HTTP_404_NOT_FOUND)

            print(f"找到申请: {application.Title}")
            print(f"当前状态: {application.review_status} ({application.get_review_status_display()})")

            # 检查申请状态：只能撤回草稿或待审核状态的申请
            if application.review_status not in [0, 1]:  # 0=草稿, 1=待审核
                status_names = {
                    0: "草稿",
                    1: "待审核",
                    2: "审核通过",
                    3: "审核不通过"
                }
                current_status = status_names.get(application.review_status, "未知")
                return Response({
                    "success": False,
                    "message": f"只能撤回草稿或待审核状态的申请，当前状态为: {current_status}",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 记录撤回信息 - 修复时间戳处理
            application_info = {
                'id': str(application.id),
                'title': application.Title,
                'type': application.Type,
                'review_status': application.review_status,
                'upload_time': application.UploadTime  # 直接使用整数时间戳，不再转换
            }

            # 删除申请
            application_title = application.Title
            application_id_str = str(application.id)
            application.delete()

            print("=== 申请撤回成功 ===")
            print(f"撤回的申请: {application_title} (ID: {application_id_str})")

            return Response({
                "success": True,
                "message": f"申请 '{application_title}' 已成功撤回",
                "data": {
                    "withdrawn_application": application_info,
                    "withdrawn_at": int(time.time() * 1000)  # 使用当前时间戳
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("撤回申请异常:", str(e))
            import traceback
            print("堆栈跟踪:", traceback.format_exc())
            return Response({
                "success": False,
                "message": f"撤回申请失败: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def find_application_safe(self, user, application_id, upload_time):
        """安全查找申请方法 - 适配新的时间戳格式"""
        print("=== 查找申请 ===")
        print(f"用户: {user.school_id}")
        print(f"申请ID: {application_id}")
        print(f"UploadTime: {upload_time}")

        # 优先使用ID查找
        if application_id:
            try:
                application = Application.objects.get(id=application_id, user=user)
                print(f"通过ID找到申请: {application.Title}")
                return application
            except Application.DoesNotExist:
                print("通过ID未找到申请")
                return None

        # 使用UploadTime查找 - 现在直接使用整数时间戳
        if upload_time:
            try:
                # 确保upload_time是整数
                if isinstance(upload_time, str):
                    upload_time = int(upload_time)

                print(f"原始UploadTime: {upload_time}")

                # 直接使用整数时间戳查找
                application = Application.objects.get(UploadTime=upload_time, user=user)
                print(f"通过UploadTime找到申请: {application.Title}")
                print(f"实际UploadTime: {application.UploadTime}")
                return application

            except Application.DoesNotExist:
                # 如果精确查找失败，尝试范围查找
                print("精确查找失败，尝试范围查找")
                time_range_start = upload_time - 5000  # 前后5秒
                time_range_end = upload_time + 5000

                applications = Application.objects.filter(
                    user=user,
                    UploadTime__range=(time_range_start, time_range_end)
                ).order_by('-UploadTime')

                if applications.exists():
                    application = applications.first()
                    print(f"通过范围查找找到申请: {application.Title}")
                    return application
                else:
                    print("通过UploadTime未找到申请")
                    return None

            except Exception as e:
                print(f"通过UploadTime查找异常: {e}")
                return None

        return None


from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from decimal import Decimal
import json
import time


class ApplicationUpdateSimpleView(APIView):
    """
    修改申请材料接口 - 支持review_status状态更新
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        """
        修改申请材料 - 支持状态从0→1的更新
        """
        try:
            print("=== 更新申请请求开始 ===")
            print(f"请求用户: {request.user.school_id}")
            print(f"请求数据: {request.data}")

            # 1. 提取并验证UploadTime
            upload_time = request.data.get('UploadTime')
            if not upload_time:
                return Response({
                    "success": False,
                    "message": "请提供申请UploadTime参数",
                    "data": None
                }, status=400)

            # 转换UploadTime为整数
            try:
                if isinstance(upload_time, str):
                    upload_time = int(upload_time)
            except (ValueError, TypeError) as e:
                print(f"UploadTime转换失败: {e}")
                return Response({
                    "success": False,
                    "message": "UploadTime参数格式错误",
                    "data": None
                }, status=400)

            # 2. 查找申请
            try:
                application = Application.objects.get(
                    UploadTime=upload_time,
                    user=request.user
                )
                print(f"✅ 找到申请: {application.Title}")
                print(f"当前状态: {application.review_status}")
            except Application.DoesNotExist:
                print(f"❌ 未找到UploadTime为{upload_time}的申请")
                return Response({
                    "success": False,
                    "message": "未找到对应的申请材料",
                    "data": None
                }, status=404)

            # 3. 检查申请状态逻辑
            current_status = application.review_status
            new_status = None

            # 检测是否提供了ReviewStatus
            if 'ReviewStatus' in request.data:
                new_status = request.data['ReviewStatus']
                if isinstance(new_status, str):
                    try:
                        new_status = int(new_status)
                    except ValueError:
                        new_status = None

                print(f"请求中的新状态: {new_status}")

                # 验证状态转换规则
                if new_status is not None:
                    # 规则1: 当前状态是草稿(0)，可以转为待审核(1)
                    if current_status == 0 and new_status == 1:
                        print("✅ 状态转换: 草稿(0) → 待审核(1)")
                        # 允许更新，后面会处理
                    # 规则2: 当前状态是草稿(0)，新状态不是1
                    elif current_status == 0 and new_status != 1:
                        print(f"⚠️ 草稿状态只能转为待审核(1)，不允许转为{new_status}")
                        # 不允许非1的状态转换，清空new_status
                        new_status = None
                    # 规则3: 当前不是草稿状态，不允许修改状态
                    elif current_status != 0:
                        print(f"⚠️ 非草稿状态不允许修改，当前状态: {current_status}")
                        new_status = None
                    # 规则4: 新状态不是有效状态
                    elif new_status not in [0, 1, 2, 3]:
                        print(f"⚠️ 无效的状态值: {new_status}")
                        new_status = None

            # 4. 使用事务确保数据一致性
            with transaction.atomic():
                # 更新基本字段
                if 'Title' in request.data:
                    application.Title = request.data['Title']
                    print(f"更新标题: {request.data['Title']}")

                # 更新类型
                if 'Type' in request.data:
                    application.Type = request.data['Type']
                    print(f"更新类型: {request.data['Type']}")

                # 更新申请分数
                if 'ApplyScore' in request.data:
                    apply_score = request.data['ApplyScore']
                    # 处理Decimal字段
                    if isinstance(apply_score, str):
                        try:
                            apply_score = Decimal(apply_score)
                        except:
                            apply_score = Decimal('0.0')
                    elif isinstance(apply_score, (int, float)):
                        apply_score = Decimal(str(apply_score))

                    application.ApplyScore = apply_score
                    print(f"更新申请分数: {float(apply_score)}")

                # 更新描述
                if 'Description' in request.data:
                    application.Description = request.data['Description']
                    print(f"更新描述: {request.data['Description'][:50]}...")

                # 更新反馈（兼容两种字段名）
                if 'FeedBack' in request.data:
                    application.Feedback = request.data['FeedBack']
                    print(f"更新反馈: {request.data['FeedBack'][:50]}...")
                elif 'Feedback' in request.data:
                    application.Feedback = request.data['Feedback']
                    print(f"更新反馈: {request.data['Feedback'][:50]}...")

                # 更新extra_data
                if 'extra_data' in request.data:
                    extra_data = request.data['extra_data']
                    if isinstance(extra_data, str):
                        try:
                            extra_data = json.loads(extra_data)
                        except json.JSONDecodeError:
                            print(f"⚠️ extra_data JSON解析失败，保持原值")
                            extra_data = application.extra_data
                    application.extra_data = extra_data
                    print(f"更新extra_data: {extra_data}")

                # 🎯 核心：更新review_status（只有符合规则时）
                if new_status is not None:
                    application.review_status = new_status
                    print(f"✅ 状态已更新: {current_status} → {new_status}")

                    # 如果状态变为待审核(1)，记录提交时间
                    if new_status == 1:
                        # 确保有提交时间记录
                        if not hasattr(application, 'submit_time') or not application.submit_time:
                            application.submit_time = int(time.time() * 1000)
                            print(f"记录提交时间: {application.submit_time}")

                # 自动更新修改时间
                application.ModifyTime = int(time.time() * 1000)
                print(f"更新修改时间: {application.ModifyTime}")

                # 保存申请
                application.save()
                print("✅ 申请数据保存成功")

                # 处理附件更新（如果需要）
                if 'Attachments' in request.data:
                    self.update_attachments(application, request.data['Attachments'])

            # 5. 序列化并返回响应
            print("=== 准备返回响应 ===")
            try:
                response_serializer = ApplicationListResponseSerializer(application)
                response_data = response_serializer.data

                return Response({
                    "success": True,
                    "message": "申请材料更新成功",
                    "data": response_data,
                    "status_changed": new_status is not None and new_status != current_status
                }, status=200)

            except Exception as serialize_error:
                print(f"❌ 序列化失败: {serialize_error}")
                import traceback
                traceback.print_exc()

                # 返回简化响应
                return Response({
                    "success": True,
                    "message": "申请材料更新成功",
                    "data": {
                        "id": str(application.id),
                        "Title": application.Title,
                        "Type": application.Type,
                        "ApplyScore": float(application.ApplyScore) if application.ApplyScore else 0.0,
                        "ReviewStatus": application.review_status,
                        "UploadTime": application.UploadTime,
                        "ModifyTime": application.ModifyTime,
                        "status_changed": new_status is not None and new_status != current_status,
                        "message": "数据已更新，详情请重新查询"
                    }
                }, status=200)

        except Exception as e:
            print(f"❌ 更新异常: {str(e)}")
            import traceback
            traceback.print_exc()

            return Response({
                "success": False,
                "message": f"修改申请失败: {str(e)}",
                "data": None
            }, status=500)

    def update_attachments(self, application, attachment_data):
        """
        更新附件关联
        """
        print("=== 更新附件关联 ===")
        print(f"原始附件数据: {attachment_data}")

        # 如果没有附件数据，清空关联
        if not attachment_data:
            application.Attachments.clear()
            if hasattr(application, 'attachments_array'):
                application.attachments_array = []
                application.save(update_fields=['attachments_array'])
            print("✅ 清空附件关联")
            return

        # 提取文件哈希
        file_hashes = []
        for item in attachment_data:
            if isinstance(item, dict):
                # 尝试多种可能的哈希字段名
                hash_value = (
                        item.get('file_hash') or
                        item.get('hash') or
                        item.get('fileHash') or
                        item.get('id')
                )
                if hash_value:
                    file_hashes.append(str(hash_value).lower().strip())
            elif isinstance(item, str):
                file_hashes.append(item.lower().strip())

        # 去重
        file_hashes = list(set([h for h in file_hashes if len(h) >= 32]))
        print(f"提取的文件哈希: {file_hashes}")

        if not file_hashes:
            # 没有有效哈希，清空关联
            application.Attachments.clear()
            if hasattr(application, 'attachments_array'):
                application.attachments_array = []
                application.save(update_fields=['attachments_array'])
            print("✅ 无有效哈希，清空附件关联")
            return

        # 查找附件
        from django.db.models import Q

        # 尝试小写和大写两种格式
        attachments = Attachment.objects.filter(
            Q(file_hash__in=file_hashes) |
            Q(file_hash__in=[h.upper() for h in file_hashes])
        ).distinct()

        print(f"找到 {attachments.count()} 个匹配的附件")

        # 更新关联
        application.Attachments.set(attachments)

        # 同步到attachments_array字段
        if hasattr(application, 'attachments_array'):
            application.attachments_array = [
                {
                    'file_hash': attach.file_hash,
                    'name': attach.name,
                    'file_url': attach.file.url if attach.file else None,
                    'size': attach.file.size if attach.file else 0
                }
                for attach in attachments
            ]
            application.save(update_fields=['attachments_array'])

        print("✅ 附件关联更新完成")


class ApplicationRevertToDraftView(APIView):
    """
    撤回申请至草稿状态 - 允许所有非草稿状态撤回
    """
    permission_classes = [IsAuthenticated]

    def find_application_safe(self, user, application_id, upload_time):
        """安全的申请查找方法 - 处理重复UploadTime"""
        print("=== 安全查找申请 ===")
        print(f"用户: {user.school_id}")
        print(f"申请ID: {application_id}")
        print(f"UploadTime: {upload_time}")

        # 优先使用application_id查找
        if application_id:
            try:
                application = Application.objects.get(id=application_id, user=user)
                print(f"✅ 通过ID找到申请: {application.Title}")
                return application
            except Application.DoesNotExist:
                print("❌ 通过ID未找到申请")
                return None
            except Exception as e:
                print(f"❌ 通过ID查找异常: {e}")
                return None

        # 其次使用UploadTime查找
        elif upload_time:
            try:
                # 确保upload_time是整数
                if isinstance(upload_time, str):
                    upload_time = int(upload_time)

                print(f"原始UploadTime: {upload_time}")

                # 使用filter而不是get，避免MultipleObjectsReturned异常
                applications = Application.objects.filter(UploadTime=upload_time, user=user)

                application_count = applications.count()
                print(f"找到 {application_count} 个匹配的申请")

                if application_count == 0:
                    print("❌ 通过UploadTime未找到申请")
                    return None

                elif application_count == 1:
                    application = applications.first()
                    print(f"✅ 通过UploadTime找到申请: {application.Title}")
                    return application

                else:
                    print(f"⚠️ 找到 {application_count} 个具有相同UploadTime的申请:")
                    for app in applications:
                        print(f"  - ID: {app.id}, Title: {app.Title}, ModifyTime: {app.ModifyTime}")

                    # 选择最新的一个（按修改时间倒序）
                    application = applications.order_by('-ModifyTime').first()
                    print(f"✅ 选择最新的申请: {application.Title}")
                    return application

            except Exception as e:
                print(f"❌ 通过UploadTime查找异常: {e}")
                return None

        else:
            print("❌ 未提供有效的查找参数")
            return None

    def put(self, request):
        """
        撤回申请至草稿状态 - 允许所有非草稿状态撤回
        PUT /api/student/material/applications/withdraw/
        """
        print("=== 撤回至草稿请求 ===")
        print(f"请求方法: {request.method}")
        print(f"请求数据: {request.data}")
        print(f"查询参数: {request.GET}")

        try:
            # 🎯 从查询参数或请求体中获取参数
            application_id = request.GET.get('id') or request.data.get('id')
            upload_time = request.GET.get('UploadTime') or request.data.get('UploadTime')

            # 确保upload_time是整数
            if upload_time and isinstance(upload_time, str):
                upload_time = int(upload_time)

            print(f"最终参数 - ID: {application_id}, UploadTime: {upload_time}")

            if not application_id and not upload_time:
                return Response({
                    "success": False,
                    "message": "请提供申请ID或UploadTime参数",
                    "data": None
                }, status=400)

            # 使用安全的查找方法
            application = self.find_application_safe(request.user, application_id, upload_time)
            if not application:
                return Response({
                    "success": False,
                    "message": "未找到对应的申请材料",
                    "data": None
                }, status=404)

            print(f"找到申请: {application.Title}, 当前状态: {application.review_status}")

            # 🎯 修改：允许所有非草稿状态撤回
            # 0=草稿, 1=待审核, 2=审核通过, 3=审核不通过
            if application.review_status == 0:  # 已经是草稿状态
                status_text = dict(Application.REVIEW_STATUS).get(application.review_status, '未知状态')
                return Response({
                    "success": False,
                    "message": f"申请已经是草稿状态，无需撤回",
                    "data": None
                }, status=400)

            # 记录原始状态用于日志
            original_status = application.review_status
            original_status_text = dict(Application.REVIEW_STATUS).get(original_status, '未知状态')

            # 执行撤回操作 - 撤回至草稿状态
            application.review_status = 0  # 撤回至草稿状态

            # 🎯 可选：清空审核相关字段（如果需要）
            # application.reviewed_by = None
            # application.reviewed_at = None
            # application.Feedback = ""
            # application.Real_Score = 0

            application.save(update_fields=['review_status'])

            print(f"✅ 撤回成功: {original_status_text}({original_status}) -> 草稿(0)")

            # 返回成功响应
            from .serializers import ApplicationListResponseSerializer
            serializer = ApplicationListResponseSerializer(application)

            return Response({
                "success": True,
                "message": f"申请已成功从{original_status_text}撤回至草稿状态",
                "data": serializer.data
            }, status=200)

        except Exception as e:
            print(f"❌ 撤回申请异常: {str(e)}")
            import traceback
            print(f"堆栈跟踪: {traceback.format_exc()}")

            return Response({
                "success": False,
                "message": f"撤回申请失败: {str(e)}",
                "data": None
            }, status=500)


import logging
from datetime import datetime, timedelta

# 定义logger
logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def teacher_review_application_with_score(request):
    """
    老师审核接口 - 审核通过时更新学业成绩
    """
    if not request.user.is_teacher:
        return Response({
            "error": "权限不足，只有老师可以审核申请"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data
        print(f"审核请求数据: {data}")

        # 支持两种参数格式
        upload_time = data.get('id')  # 时间戳格式
        application_id = data.get('application_id')  # UUID格式
        result = data.get('result')
        comment = data.get('comment', '')

        # 参数验证
        if not any([upload_time, application_id]):
            return Response({
                "error": "请提供申请标识参数: id(时间戳) 或 application_id(UUID)"
            }, status=400)

        if result is None:
            return Response({
                "error": "缺少审核结果参数: result"
            }, status=400)

        application = None

        # 方式1: 使用application_id查找（最可靠）
        if application_id:
            try:
                application = Application.objects.get(id=application_id)
                print(f"通过application_id找到申请: {application.id}")
            except Application.DoesNotExist:
                print(f"通过application_id未找到申请: {application_id}")

        # 方式2: 使用upload_time查找
        if not application and upload_time:
            try:
                application = Application.objects.get(UploadTime=upload_time)
                print(f"通过upload_time精确找到申请: {application.id}")
            except Application.DoesNotExist:
                print("精确查找失败，尝试范围查找")
                time_range_start = upload_time - 5000
                time_range_end = upload_time + 5000

                applications = Application.objects.filter(
                    UploadTime__range=(time_range_start, time_range_end),
                    review_status=1
                )
                if applications.exists():
                    application = applications.first()
                    print(f"通过范围查找找到申请: {application.id}")

        if not application:
            return Response({
                "error": "申请不存在"
            }, status=404)

        # 状态验证
        if application.review_status != 1:
            return Response({
                "error": "申请状态不正确，只能审核待审核的申请",
                "current_status": application.review_status
            }, status=400)

        # 更新申请状态
        new_status = 2 if result else 3
        print(f"更新状态: {application.review_status} -> {new_status}")

        application.review_status = new_status

        # 设置实际得分
        if result:
            apply_score = getattr(application, 'ApplyScore', 0)
            if hasattr(application, 'Real_Score'):
                application.Real_Score = apply_score
            elif hasattr(application, 'RealScore'):
                application.RealScore = apply_score
            print(f"设置实际得分: {apply_score}")
        else:
            if hasattr(application, 'Real_Score'):
                application.Real_Score = 0
            elif hasattr(application, 'RealScore'):
                application.RealScore = 0
            print("审核不通过，实际得分设为0")

        # 设置反馈
        if hasattr(application, 'Feedback'):
            application.Feedback = comment
        elif hasattr(application, 'FeedBack'):
            application.FeedBack = comment

        # 更新时间戳
        application.ModifyTime = int(time.time() * 1000)

        # 记录审核老师
        if hasattr(application, 'reviewed_by'):
            application.reviewed_by = request.user

        # 🎯 关键：如果审核通过，更新学业成绩
        if result:  # 审核通过
            try:
                update_academic_performance_score(application)
                print("✅ 审核通过，学业成绩已更新")
            except Exception as e:
                print(f"⚠️ 学业成绩更新失败: {str(e)}")

        application.save()

        print("审核成功完成")

        return Response({
            "success": True,
            "message": "审核完成",
            "data": {
                "application_id": str(application.id),
                "upload_time": application.UploadTime,
                "previous_status": 1,
                "new_status": new_status,
                "real_score": getattr(application, 'Real_Score', getattr(application, 'RealScore', 0)),
                "feedback": comment,
                "student_name": application.user.name,
                "title": getattr(application, 'Title', '')
            }
        })

    except Exception as e:
        print(f"审核过程中发生错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return Response({
            "error": f"审核失败: {str(e)}"
        }, status=500)


from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from decimal import Decimal
import time


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def teacher_update_review_with_score(request):
    """
    老师重新审核接口 - 兼容新旧参数格式
    """
    print("=== 教师重新审核开始 ===")
    print(f"操作教师: {request.user.school_id}")
    print(f"请求数据: {request.data}")

    # 1. 权限检查
    if not hasattr(request.user, 'user_type') or request.user.user_type != 1:
        print("❌ 权限不足：用户不是教师")
        return Response({
            "success": False,
            "message": "权限不足，只有老师可以重新审核申请"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data

        # 2. 🎯 关键修复：兼容多种参数格式
        # 支持: UploadTime, id, application_id 等字段名
        upload_time = (
                data.get('UploadTime') or
                data.get('upload_time') or
                data.get('id') or
                data.get('application_id') or
                data.get('applicationId')
        )

        print(f"提取的标识符: {upload_time} (类型: {type(upload_time)})")

        # 支持多种反馈字段名
        feedback = (
                data.get('comment') or
                data.get('feedback') or
                data.get('FeedBack') or
                data.get('Feedback') or
                data.get('review_comment') or
                ''
        )

        print(f"提取的反馈: {feedback}")

        # 3. 🎯 核心修复：支持result布尔值格式
        real_score = None

        # 情况1: 有Real_Score字段，直接使用
        if 'Real_Score' in data:
            real_score = data['Real_Score']
            print(f"使用Real_Score字段: {real_score}")

        # 情况2: 有RealScore字段，直接使用
        elif 'RealScore' in data:
            real_score = data['RealScore']
            print(f"使用RealScore字段: {real_score}")

        # 情况3: 🎯 兼容旧格式：使用result布尔值和ApplyScore计算
        elif 'result' in data:
            # 先查找申请，获取ApplyScore
            try:
                # 处理时间戳格式
                identifier = upload_time
                if isinstance(identifier, str):
                    identifier = int(float(identifier))

                # 查找申请
                application = Application.objects.get(UploadTime=identifier)
                apply_score = getattr(application, 'ApplyScore', 0)

                # 根据result计算分数
                if data['result'] is True or data['result'] == 'true' or data['result'] == 'True':
                    real_score = float(apply_score) if apply_score else 0
                    print(f"result=True，使用ApplyScore: {real_score}")
                else:
                    real_score = 0
                    print(f"result=False，分数设为0")

            except Exception as e:
                print(f"⚠️ 解析result格式失败: {e}")
                real_score = 0

        else:
            print("❌ 缺少分数参数")
            return Response({
                "success": False,
                "message": "请提供分数参数: Real_Score 或 result"
            }, status=400)

        # 4. 参数验证
        if not upload_time:
            print("❌ 缺少申请标识符参数")
            return Response({
                "success": False,
                "message": "请提供申请标识参数: id 或 UploadTime"
            }, status=400)

        # 5. 处理时间戳格式
        try:
            if isinstance(upload_time, str):
                upload_time = int(float(upload_time))
            elif isinstance(upload_time, (int, float)):
                upload_time = int(upload_time)
            print(f"标准化后的UploadTime: {upload_time}")
        except (ValueError, TypeError) as e:
            print(f"❌ 时间戳格式错误: {e}, 原始值: {data.get('id')}")
            return Response({
                "success": False,
                "message": "申请标识符格式错误"
            }, status=400)

        # 6. 查找申请
        print(f"查找申请: UploadTime={upload_time}")
        try:
            application = Application.objects.get(UploadTime=upload_time)
            print(f"✅ 找到申请: ID={application.id}, 标题={application.Title}")
        except Application.DoesNotExist:
            # 尝试范围查找
            print("精确查找失败，尝试范围查找")
            time_range_start = upload_time - 5000
            time_range_end = upload_time + 5000

            applications = Application.objects.filter(
                UploadTime__range=(time_range_start, time_range_end)
            )
            if applications.exists():
                application = applications.first()
                print(f"✅ 通过范围查找找到申请: ID={application.id}")
            else:
                print(f"❌ 未找到UploadTime为{upload_time}的申请")
                return Response({
                    "success": False,
                    "message": "申请不存在"
                }, status=404)

        # 7. 调试信息
        print(f"申请信息:")
        print(f"  - 学生: {application.user.school_id}")
        print(f"  - 当前状态: {application.review_status}")
        print(f"  - ApplyScore: {application.ApplyScore}")

        # 获取原始信息
        original_score = getattr(application, 'Real_Score', getattr(application, 'RealScore', None))
        original_feedback = getattr(application, 'Feedback', getattr(application, 'FeedBack', ''))

        print(f"  - 原始分数: {original_score}")
        print(f"  - 原始反馈: {original_feedback[:50] if original_feedback else '空'}")

        # 8. 使用事务更新
        with transaction.atomic():
            # 处理分数格式
            try:
                if isinstance(real_score, str):
                    real_score = Decimal(real_score)
                elif isinstance(real_score, (int, float)):
                    real_score = Decimal(str(real_score))
                print(f"处理后的分数: {real_score} (类型: {type(real_score)})")
            except Exception as e:
                print(f"❌ 分数格式转换失败: {e}")
                return Response({
                    "success": False,
                    "message": "分数格式不正确"
                }, status=400)

            # 🎯 更新分数 - 直接覆盖
            print(f"更新分数: {original_score} → {real_score}")

            if hasattr(application, 'Real_Score'):
                application.Real_Score = real_score
                print("使用Real_Score字段")
            elif hasattr(application, 'RealScore'):
                application.RealScore = real_score
                print("使用RealScore字段")
            else:
                # 如果模型没有分数字段，使用extra_data存储
                if not application.extra_data:
                    application.extra_data = {}
                application.extra_data['real_score'] = float(real_score)
                print("使用extra_data存储分数")

            # 🎯 更新反馈 - 直接覆盖
            if feedback is not None:
                print(
                    f"更新反馈: {original_feedback[:50] if original_feedback else '空'} → {feedback[:50] if feedback else '空'}")

                if hasattr(application, 'Feedback'):
                    application.Feedback = feedback
                    print("使用Feedback字段")
                elif hasattr(application, 'FeedBack'):
                    application.FeedBack = feedback
                    print("使用FeedBack字段")
                else:
                    # 使用extra_data存储
                    if not application.extra_data:
                        application.extra_data = {}
                    application.extra_data['feedback'] = feedback
                    print("使用extra_data存储反馈")

            # 更新修改时间
            application.ModifyTime = int(time.time() * 1000)
            print(f"更新修改时间: {application.ModifyTime}")

            # 记录操作老师（可选）
            if hasattr(application, 'last_reviewed_by'):
                application.last_reviewed_by = request.user
                print(f"记录操作老师: {request.user.school_id}")

            # 保存申请
            application.save()
            print("✅ 申请更新保存成功")

            # 9. 更新学业成绩
            try:
                # 刷新对象获取最新数据
                application.refresh_from_db()
                update_academic_performance_score(application)
                print("✅ 学业成绩更新成功")
            except Exception as e:
                print(f"⚠️ 学业成绩更新失败: {e}")
                # 学业成绩更新失败不影响主流程

        # 10. 返回成功响应
        print("=== 重新审核完成 ===")
        return Response({
            "success": True,
            "message": "重新审核完成",
            "data": {
                "application_id": str(application.id),
                "upload_time": application.UploadTime,
                "title": application.Title,
                "student_id": application.user.school_id,
                "student_name": getattr(application.user, 'name', ''),
                "old_score": float(original_score) if original_score else None,
                "new_score": float(real_score),
                "old_feedback": original_feedback,
                "new_feedback": feedback,
                "review_status": application.review_status,
                "modify_time": application.ModifyTime,
                "result_processed": 'result' in data  # 标记是否使用了result格式
            }
        })

    except Exception as e:
        print(f"❌ 重新审核过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

        return Response({
            "success": False,
            "message": f"重新审核失败: {str(e)}"
        }, status=500)


def update_academic_performance_score(application):
    """
    更新学业成绩表中的加分项
    简化版：只更新分数，不进行复杂计算
    """
    try:
        print(f"更新学业成绩: 用户={application.user.school_id}, 分数={application.Real_Score}")

        # 获取或创建学业成绩记录
        academic_perf, created = AcademicPerformance.objects.get_or_create(
            user=application.user,
            defaults={'bonus_points': 0}
        )

        # 获取该申请类型对应的分数
        score = getattr(application, 'Real_Score', getattr(application, 'RealScore', 0))
        if score:
            # 将Decimal转换为float存储
            bonus_points = float(score)

            # 更新加分项（可以根据申请类型进行累加或其他逻辑）
            # 这里简化：直接设置或累加
            if hasattr(academic_perf, 'bonus_points'):
                academic_perf.bonus_points = bonus_points
            elif hasattr(academic_perf, 'additional_score'):
                academic_perf.additional_score = bonus_points

            academic_perf.save()
            print(f"学业成绩更新完成: 加分={bonus_points}")

    except Exception as e:
        print(f"学业成绩更新异常: {e}")
        # 允许失败，不影响主流程


def _create_rereview_history(self, application, teacher, old_score, new_score, old_comment, new_comment):
    """
    创建重新审核历史记录
    """
    try:
        # 如果项目中有审核历史模型
        from .models import ReviewHistory

        ReviewHistory.objects.create(
            application=application,
            teacher=teacher,
            action_type='RE_REVIEW',
            old_score=old_score,
            new_score=new_score,
            old_comment=old_comment,
            new_comment=new_comment,
            created_time=int(timezone.now().timestamp() * 1000)
        )
    except Exception as e:
        # 记录日志但不阻断主流程
        print(f"创建重新审核历史记录失败: {str(e)}")


@api_view(['POST', 'PUT'])
@permission_classes([IsAuthenticated])
def teacher_revoke_review(request):
    """
    老师撤销审核接口 - 增强调试版本，带学业成绩重置
    """
    print(f"撤销审核请求方法: {request.method}")
    print(f"请求数据: {request.data}")
    print(f"用户: {request.user}, 用户类型: {getattr(request.user, 'user_type', '未知')}")

    # 权限验证
    if not request.user.is_teacher:
        return Response({
            "error": "权限不足，只有老师可以撤销审核"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data
        upload_time = data.get('UploadTime') or data.get('id')

        if not upload_time:
            return Response({
                "error": "请提供申请标识参数: UploadTime 或 id"
            }, status=400)

        print(f"使用标识查找申请: {upload_time}")

        # 🔍 增强查找逻辑
        application = None
        found_by = None

        try:
            # 1. 精确查找
            application = Application.objects.get(UploadTime=upload_time)
            found_by = "精确查找"
            print(f"精确找到申请: {application.id}, 状态: {application.review_status}")
        except Application.DoesNotExist:
            print(f"精确查找失败: UploadTime={upload_time} 不存在")

            # 2. 范围查找
            time_range_start = upload_time - 5000
            time_range_end = upload_time + 5000

            applications = Application.objects.filter(
                UploadTime__range=(time_range_start, time_range_end)
            )

            if applications.exists():
                application = applications.first()
                found_by = f"范围查找 ({len(applications)} 个匹配)"
                print(
                    f"范围查找找到申请: {application.id}, 实际UploadTime: {application.UploadTime}, 状态: {application.review_status}")
            else:
                print(f"范围查找失败: 在范围 [{time_range_start}, {time_range_end}] 内未找到申请")
                return Response({
                    "error": f"未找到申请记录 (标识: {upload_time})",
                    "debug": {
                        "provided_upload_time": upload_time,
                        "search_range": [time_range_start, time_range_end]
                    }
                }, status=404)

        # 🎯 详细的状态检查
        current_status = application.review_status
        status_display = getattr(application, 'get_review_status_display', lambda: '未知')()

        print(f"申请状态检查: {current_status} ({status_display})")
        print(f"允许撤销的状态: [2, 3]")

        if current_status not in [2, 3]:
            return Response({
                "error": "申请状态不正确，只能撤销已审核的申请",
                "details": {
                    "current_status": current_status,
                    "current_status_display": status_display,
                    "allowed_status": [2, 3],
                    "application_id": str(application.id),
                    "found_by": found_by
                }
            }, status=400)

        # 📝 记录原始信息
        original_status = current_status
        original_score = getattr(application, 'RealScore', getattr(application, 'Real_Score', 0))
        application_type = application.Type  # 记录申请类型用于重置成绩

        print(f"开始撤销: 状态 {original_status} -> 1, 分数 {original_score} -> 0")

        # 🔄 执行撤销操作
        application.review_status = 1  # 待审核

        # 重置分数
        if hasattr(application, 'RealScore'):
            application.RealScore = 0
        elif hasattr(application, 'Real_Score'):
            application.Real_Score = 0

        # 更新反馈
        feedback_text = f"审核已由{request.user.name}撤销，等待重新审核"
        if hasattr(application, 'FeedBack'):
            application.FeedBack = feedback_text
        elif hasattr(application, 'Feedback'):
            application.Feedback = feedback_text

        # 更新时间戳
        import time
        application.ModifyTime = int(time.time() * 1000)

        # 记录操作老师
        if hasattr(application, 'last_reviewed_by'):
            application.last_reviewed_by = request.user

        # 🎯 关键：撤销审核时重置学业成绩中的对应项目分数
        try:
            reset_academic_performance_score(application)
            print("✅ 学业成绩已重置")
        except Exception as e:
            print(f"⚠️ 学业成绩重置失败: {str(e)}")
            # 不阻断主流程，继续保存申请

        application.save()

        print(f"撤销成功: 状态 {original_status} -> {application.review_status}")

        return Response({
            "success": True,
            "message": "审核已撤销，申请状态已重置为待审核",
            "data": {
                "application_id": str(application.id),
                "upload_time": application.UploadTime,
                "previous_status": original_status,
                "new_status": 1,
                "student_name": application.user.name,
                "found_by": found_by,
                "score_reset": True  # 表示分数已重置
            }
        }, status=200)

    except Application.MultipleObjectsReturned:
        print(f"找到多个相同UploadTime的申请: {upload_time}")
        return Response({
            "error": "找到多个相同标识的申请记录，请联系管理员",
            "details": f"UploadTime: {upload_time}"
        }, status=400)
    except Exception as e:
        print(f"撤销审核错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return Response({
            "error": f"撤销审核失败: {str(e)}",
            "details": "服务器内部错误，请查看日志"
        }, status=500)


def reset_academic_performance_score(application):
    """
    撤销审核时重置学业成绩中的对应项目分数为0
    """
    try:
        from django.db import transaction
        from decimal import Decimal

        with transaction.atomic():
            # 获取学生和学业成绩记录
            student = application.user
            academic_perf, created = AcademicPerformance.objects.get_or_create(
                user=student
            )

            # 获取申请类型
            application_type = application.Type

            print(f"重置学业成绩: 学生={student.name}, 申请类型={application_type}, 重置分数=0")

            # 根据申请类型重置对应的成绩字段为0
            if application_type in AcademicPerformance.SCORE_TYPES:
                score_type_name = AcademicPerformance.SCORE_TYPES[application_type]
                academic_perf.set_score(application_type, 0)  # 重置为0

                print(f"重置 {score_type_name}[{application_type}] = 0")

                # 重新计算总分
                recalculate_total_scores(academic_perf)

                academic_perf.save()
                print(f"学业成绩重置完成")
            else:
                print(f"未知的申请类型: {application_type}")

    except Exception as e:
        print(f"重置学业成绩失败: {str(e)}")
        raise


def recalculate_total_scores(academic_perf):
    """
    重新计算学业专长成绩和总分
    """
    try:
        from decimal import Decimal

        # 计算学术专长成绩（前4项，满分15分）
        academic_expertise_scores = []
        for i in range(4):  # 0-3: 学术竞赛、创新训练、学术研究、荣誉称号
            if i < len(academic_perf.applications_score):
                score = academic_perf.applications_score[i]
                academic_expertise_scores.append(min(float(score), 5.0))  # 每项最高5分

        academic_expertise_total = sum(academic_expertise_scores)
        academic_perf.academic_expertise_score = Decimal(str(min(academic_expertise_total, 15.0)))  # 满分15分

        # 计算综合表现成绩（后5项，满分5分）
        comprehensive_scores = []
        for i in range(4, 9):  # 4-8: 社会工作、志愿服务、国际实习、参军入伍、体育项目
            if i < len(academic_perf.applications_score):
                score = academic_perf.applications_score[i]
                comprehensive_scores.append(min(float(score), 1.0))  # 每项最高1分

        comprehensive_total = sum(comprehensive_scores)
        academic_perf.comprehensive_performance_score = Decimal(str(min(comprehensive_total, 5.0)))  # 满分5分

        # 计算总分（学业成绩 + 学术专长 + 综合表现）
        total_score = (
                academic_perf.academic_score +
                academic_perf.academic_expertise_score +
                academic_perf.comprehensive_performance_score
        )
        academic_perf.total_comprehensive_score = Decimal(str(min(total_score, 100.0)))  # 满分100分

        print(f"重新计算总分: 学业={academic_perf.academic_score}, "
              f"学术专长={academic_perf.academic_expertise_score}, "
              f"综合表现={academic_perf.comprehensive_performance_score}, "
              f"总分={academic_perf.total_comprehensive_score}")

    except Exception as e:
        print(f"重新计算总分失败: {str(e)}")
        raise


def create_review_history(application, original_status, original_score, original_reviewer, updated_by):
    """创建审核更改历史记录"""
    # 这里可以实现审核历史记录功能
    # 例如保存到专门的ReviewHistory模型
    pass


def create_revoke_history(application, original_status, original_score, original_reviewer, revoked_by):
    """创建撤销审核历史记录"""
    # 这里可以实现撤销审核历史记录功能
    pass


def update_academic_performance_score(application):
    """更新学业成绩表中的对应分数"""

    try:
        # 获取学生用户的学业成绩记录
        academic_perf, created = AcademicPerformance.objects.get_or_create(
            user=application.user
        )

        # 根据申请类型更新对应的分数字段
        score_type = application.Type
        if application.ReviewStatus == 2:  # 审核通过
            score_value = application.RealScore
        else:  # 审核不通过或其他状态
            score_value = 0

        # 使用智能映射方法设置分数
        academic_perf.set_score(score_type, score_value)
        academic_perf.save()

    except Exception as e:
        # 记录错误但不中断主流程
        print(f"更新学业成绩失败: {e}")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pending_applications(request):
    """
    老师获取所有待审核申请接口
    GET /api/student/material/pending_list/
    """
    # 权限验证 - 必须是老师
    if not request.user.is_teacher:
        return Response({
            "error": "权限不足，只有老师可以查看待审核申请"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        # 修复字段名：使用 review_status 而不是 ReviewStatus
        queryset = Application.objects.filter(review_status=1)  # 待审核状态

        # 应用过滤器
        application_type = request.GET.get('type')
        college = request.GET.get('college')

        if application_type is not None:
            try:
                application_type = int(application_type)
                queryset = queryset.filter(Type=application_type)
            except (ValueError, TypeError):
                return Response({
                    "error": "申请类型参数格式错误"
                }, status=status.HTTP_400_BAD_REQUEST)

        if college:
            queryset = queryset.filter(user__college=college)

        # 预取关联数据以提高性能
        queryset = queryset.select_related('user')

        # 序列化数据 - 直接返回所有数据，不分页
        serializer = SafeTeacherPendingApplicationListSerializer(queryset, many=True)

        return Response({
            "ApplyList": serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        print("Error in get_pending_applications:")
        print(traceback.format_exc())

        return Response({
            "error": "获取待审核申请失败",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_review_history(request):
    """
    获取审核历史记录 - 根据实际User模型修复
    """
    user = request.user

    # 🎯 权限验证：老师和管理员都可以访问
    user_type = getattr(user, 'user_type', 0)
    if user_type not in [1, 2]:  # 1=老师, 2=管理员
        return Response({
            "error": "权限不足，只有老师和管理员可以访问审核历史",
            "debug": f"用户类型: {user_type} (需要: 1或2)"
        }, status=status.HTTP_403_FORBIDDEN)

    # 🎯 使用正确的用户标识字段
    user_identifier = f"{user.name}({user.school_id})"

    print(f"审核历史访问: 用户ID={user.id}, 姓名={user.name}, 工号={user.school_id}, 用户类型={user_type}")
    print(f"请求参数: {request.GET}")

    try:
        # 🔍 构建查询集 - 所有已审核的申请
        queryset = Application.objects.filter(
            review_status__in=[2, 3]  # 审核通过和不通过
        )

        # 🎯 权限过滤逻辑
        is_admin = (user_type == 2)

        # 🎯 修复参数获取：支持 id 和 teacher_id 参数
        target_teacher_param = request.GET.get('teacher_id') or request.GET.get('id')

        filter_description = ""

        if is_admin and target_teacher_param:
            # 🎯 管理员模式：查看指定老师的审核记录
            try:
                target_teacher = None

                target_teacher = User.objects.get(school_id=target_teacher_param, user_type=1)
                print(f"按工号找到老师: {target_teacher.name} (工号: {target_teacher.school_id})")

                # 根据审核老师字段过滤
                if hasattr(Application, 'reviewed_by'):
                    queryset = queryset.filter(reviewed_by=target_teacher)
                    filter_description = f"管理员查看老师 {target_teacher.name}({target_teacher.school_id}) 的审核记录"
                elif hasattr(Application, 'review_teacher'):
                    queryset = queryset.filter(review_teacher=target_teacher)
                    filter_description = f"管理员查看老师 {target_teacher.name}({target_teacher.school_id}) 的审核记录"
                elif hasattr(Application, 'last_reviewed_by'):
                    queryset = queryset.filter(last_reviewed_by=target_teacher)
                    filter_description = f"管理员查看老师 {target_teacher.name}({target_teacher.school_id}) 的审核记录"
                else:
                    queryset = queryset.none()
                    filter_description = "无审核老师字段，返回空结果"

                print(f"管理员模式: 查看老师 {target_teacher.name} 的审核记录")

            except User.DoesNotExist:
                # 提供可用的老师列表
                available_teachers = User.objects.filter(user_type=1).values('id', 'school_id', 'name', 'college')[:10]
                return Response({
                    "error": "指定的老师不存在或不是老师用户",
                    "provided_identifier": target_teacher_param,
                    "available_teachers": list(available_teachers),
                    "suggestion": "请使用老师工号（如 T0002）或正确的用户ID"
                }, status=status.HTTP_404_NOT_FOUND)

        elif is_admin and not target_teacher_param:
            # 管理员但没有指定老师：返回错误提示
            return Response({
                "error": "管理员请提供teacher_id或id参数来查看特定老师的审核记录",
                "example": "/api/student/material/reviews/history/?teacher_id=T0002",
                "available_teachers_example": "使用工号如 T0001, T0002 等"
            }, status=status.HTTP_400_BAD_REQUEST)

        else:
            # 🎯 老师模式：只查看自己的审核记录
            if hasattr(Application, 'reviewed_by'):
                queryset = queryset.filter(reviewed_by=user)
                filter_description = f"老师查看自己的审核记录 (用户: {user.name}({user.school_id}))"
            elif hasattr(Application, 'review_teacher'):
                queryset = queryset.filter(review_teacher=user)
                filter_description = f"老师查看自己的审核记录 (用户: {user.name}({user.school_id}))"
            elif hasattr(Application, 'last_reviewed_by'):
                queryset = queryset.filter(last_reviewed_by=user)
                filter_description = f"老师查看自己的审核记录 (用户: {user.name}({user.school_id}))"
            else:
                queryset = queryset.none()
                filter_description = "无审核老师字段，返回空结果"

            print(f"老师模式: 只查看自己的审核记录")

        # 📋 应用其他查询过滤器
        application_type = request.GET.get('type')
        college = request.GET.get('college')
        student_name = request.GET.get('student_name')

        if application_type is not None:
            try:
                application_type = int(application_type)
                queryset = queryset.filter(Type=application_type)
                print(f"按申请类型过滤: {application_type}")
            except (ValueError, TypeError):
                return Response({
                    "error": "申请类型参数格式错误"
                }, status=status.HTTP_400_BAD_REQUEST)

        if college:
            queryset = queryset.filter(user__college=college)
            print(f"按学院过滤: {college}")

        if student_name:
            queryset = queryset.filter(
                Q(user__name__icontains=student_name) |
                Q(user__school_id__icontains=student_name)
            )
            print(f"按学生姓名过滤: {student_name}")

        # 🔍 预取关联数据以提高性能
        queryset = queryset.select_related('user')
        if hasattr(Application, 'reviewed_by'):
            queryset = queryset.select_related('reviewed_by')

        # 排序：按审核时间倒序
        if hasattr(Application, 'reviewed_at'):
            queryset = queryset.order_by('-reviewed_at')
        elif hasattr(Application, 'ModifyTime'):
            queryset = queryset.order_by('-ModifyTime')
        else:
            queryset = queryset.order_by('-id')

        total_count = queryset.count()
        print(f"最终查询结果: {total_count} 条记录")

        # 📊 序列化数据
        serializer = SafeTeacherPendingApplicationListSerializer(queryset, many=True)

        response_data = {
            "success": True,
            "count": total_count,
            "user_role": "管理员" if is_admin else "老师",
            "ApplyList": serializer.data
        }

        # 管理员模式下返回老师信息
        if is_admin and target_teacher_param and 'target_teacher' in locals():
            response_data["teacher_info"] = {
                "id": str(target_teacher.id),
                "school_id": target_teacher.school_id,
                "name": target_teacher.name,
                "college": target_teacher.college,
                "title": target_teacher.title
            }
            response_data["target_teacher"] = target_teacher_param

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        print("Error in teacher_review_history:")
        print(traceback.format_exc())

        return Response({
            "error": "获取审核历史失败",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def update_academic_performance_score(application):
    """
    更新学生学业成绩中的申请项目分数
    """
    try:
        from django.db import transaction
        from decimal import Decimal

        with transaction.atomic():
            # 获取学生和学业成绩记录
            student = application.user
            academic_perf, created = AcademicPerformance.objects.get_or_create(
                user=student
            )

            # 获取申请类型和实际得分
            application_type = application.Type
            real_score = getattr(application, 'Real_Score', getattr(application, 'RealScore', 0))

            print(f"更新学业成绩: 学生={student.name}, 申请类型={application_type}, 得分={real_score}")

            # 根据申请类型更新对应的成绩字段
            if application_type in AcademicPerformance.SCORE_TYPES:
                score_type_name = AcademicPerformance.SCORE_TYPES[application_type]
                academic_perf.set_score(application_type, real_score)

                print(f"设置 {score_type_name}[{application_type}] = {real_score}")

                # 重新计算总分
                recalculate_total_scores(academic_perf)

                academic_perf.save()
                print(f"学业成绩更新完成")
            else:
                print(f"未知的申请类型: {application_type}")

    except Exception as e:
        print(f"更新学业成绩失败: {str(e)}")
        raise


def recalculate_total_scores(academic_perf):
    """
    重新计算学业专长成绩和总分
    """
    try:
        from decimal import Decimal

        # 计算学术专长成绩（前4项，满分15分）
        academic_expertise_scores = []
        for i in range(4):  # 0-3: 学术竞赛、创新训练、学术研究、荣誉称号
            if i < len(academic_perf.applications_score):
                score = academic_perf.applications_score[i]
                academic_expertise_scores.append(min(float(score), 5.0))  # 每项最高5分

        academic_expertise_total = sum(academic_expertise_scores)
        academic_perf.academic_expertise_score = Decimal(str(min(academic_expertise_total, 15.0)))  # 满分15分

        # 计算综合表现成绩（后5项，满分5分）
        comprehensive_scores = []
        for i in range(4, 9):  # 4-8: 社会工作、志愿服务、国际实习、参军入伍、体育项目
            if i < len(academic_perf.applications_score):
                score = academic_perf.applications_score[i]
                comprehensive_scores.append(min(float(score), 1.0))  # 每项最高1分

        comprehensive_total = sum(comprehensive_scores)
        academic_perf.comprehensive_performance_score = Decimal(str(min(comprehensive_total, 5.0)))  # 满分5分

        # 计算总分（学业成绩 + 学术专长 + 综合表现）
        total_score = (
                academic_perf.academic_score +
                academic_perf.academic_expertise_score +
                academic_perf.comprehensive_performance_score
        )
        academic_perf.total_comprehensive_score = Decimal(str(min(total_score, 100.0)))  # 满分100分

        print(f"重新计算总分: 学业={academic_perf.academic_score}, "
              f"学术专长={academic_perf.academic_expertise_score}, "
              f"综合表现={academic_perf.comprehensive_performance_score}, "
              f"总分={academic_perf.total_comprehensive_score}")

    except Exception as e:
        print(f"重新计算总分失败: {str(e)}")
        raise