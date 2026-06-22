content = open('/app/syblog_project/blog/views.py').read()

# 1) history 뷰에 task 상태 포함
old_history = '''def ai_webdev_history(request, pk):
    """프로젝트 대화 이력 JSON 반환"""
    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    sessions = AiWebSession.objects.filter(project=project).order_by('created_at')
    return JsonResponse({
        'history': [
            {
                'id': s.pk,
                'role': s.role,
                'content': s.content,
                'tool_calls': s.tool_calls,
                'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for s in sessions
        ]
    })'''

new_history = '''def ai_webdev_history(request, pk):
    """프로젝트 대화 이력 JSON 반환 (+ 실행중 task 상태)"""
    from blog.models import AiWebProject, AiWebSession, AiWebTask
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    sessions = AiWebSession.objects.filter(project=project).order_by('created_at')

    # 실행중 task 조회
    running_task = AiWebTask.objects.filter(
        project=project, status=AiWebTask.STATUS_RUNNING
    ).order_by('-created_at').first()

    task_info = None
    if running_task:
        task_info = {
            'id': running_task.pk,
            'status': running_task.status,
            'label': running_task.label or '명령 실행 중...',
            'updated_at': running_task.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        }

    return JsonResponse({
        'history': [
            {
                'id': s.pk,
                'role': s.role,
                'content': s.content,
                'tool_calls': s.tool_calls,
                'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for s in sessions
        ],
        'running_task': task_info,
    })'''

if old_history in content:
    content = content.replace(old_history, new_history, 1)
    print("✅ history 뷰 수정 완료")
else:
    print("❌ history 뷰 패턴 불일치")

# 2) task status / update API 추가 (clear_history 뷰 뒤에 삽입)
task_api = '''

@login_required
def ai_webdev_task_status(request, pk):
    """실행중 task 상태 조회"""
    from blog.models import AiWebProject, AiWebTask
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    task = AiWebTask.objects.filter(project=project, status=AiWebTask.STATUS_RUNNING).order_by('-created_at').first()
    if task:
        return JsonResponse({
            'running': True,
            'id': task.pk,
            'label': task.label or '명령 실행 중...',
            'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return JsonResponse({'running': False})


@login_required
def ai_webdev_task_upsert(request, pk):
    """task 상태 생성/업데이트 (프런트에서 호출)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    from blog.models import AiWebProject, AiWebTask
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    try:
        body = _json_mod.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    action     = body.get('action', 'start')   # start | update | done | error | cancel
    label      = body.get('label', '')
    result_msg = body.get('result_msg', '')
    error_msg  = body.get('error_msg', '')
    task_id    = body.get('task_id')

    if action == 'start':
        # 이전 running task 정리
        AiWebTask.objects.filter(project=project, status=AiWebTask.STATUS_RUNNING).update(
            status=AiWebTask.STATUS_CANCELLED
        )
        task = AiWebTask.objects.create(project=project, status=AiWebTask.STATUS_RUNNING, label=label)
        return JsonResponse({'ok': True, 'task_id': task.pk})

    elif action in ('update', 'done', 'error', 'cancel'):
        qs = AiWebTask.objects.filter(project=project)
        if task_id:
            qs = qs.filter(pk=task_id)
        else:
            qs = qs.filter(status=AiWebTask.STATUS_RUNNING)
        task = qs.order_by('-created_at').first()
        if not task:
            return JsonResponse({'error': 'task 없음'}, status=404)

        if action == 'update':
            task.label = label or task.label
            task.save(update_fields=['label', 'updated_at'])
        elif action == 'done':
            task.status = AiWebTask.STATUS_DONE
            task.result_msg = result_msg
            task.label = label or '작업 완료'
            task.save()
        elif action == 'error':
            task.status = AiWebTask.STATUS_ERROR
            task.error_msg = error_msg
            task.label = label or '오류 발생'
            task.save()
        elif action == 'cancel':
            task.status = AiWebTask.STATUS_CANCELLED
            task.save()
        return JsonResponse({'ok': True, 'task_id': task.pk, 'status': task.status})

    return JsonResponse({'error': '알 수 없는 action'}, status=400)

'''

# clear_history 다음에 삽입
insert_marker = '@login_required\ndef ai_webdev_files(request, pk):'
if insert_marker in content:
    content = content.replace(insert_marker, task_api + insert_marker, 1)
    print("✅ task API 추가 완료")
else:
    # 다른 마커 시도
    insert_marker2 = '@login_required\ndef ai_webdev_deploy'
    if insert_marker2 in content:
        content = content.replace(insert_marker2, task_api + insert_marker2, 1)
        print("✅ task API 추가 완료 (대체 마커)")
    else:
        print("❌ 삽입 마커 못 찾음")
        # 파일 끝에 추가
        content = content + task_api
        print("✅ task API 파일 끝에 추가")

open('/app/syblog_project/blog/views.py', 'w').write(content)
print("✅ views.py 저장 완료")
