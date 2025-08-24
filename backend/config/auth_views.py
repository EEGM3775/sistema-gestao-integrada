# backend/config/auth_views.py
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
import json

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """
    API endpoint para login que retorna token JWT
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return Response({
                'error': 'Username e password são obrigatórios'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Autenticar usuário
        user = authenticate(username=username, password=password)
        
        if user:
            if user.is_active:
                # Gerar tokens JWT
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                
                return Response({
                    'success': True,
                    'access_token': str(access_token),
                    'refresh_token': str(refresh),
                    'user': {
                        'id': user.pk,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                    }
                })
            else:
                return Response({
                    'error': 'Conta desativada'
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({
                'error': 'Credenciais inválidas'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
    except json.JSONDecodeError:
        return Response({
            'error': 'JSON inválido'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': f'Erro interno: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def api_logout(request):
    """
    API endpoint para logout (blacklist do token)
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        return Response({
            'success': True,
            'message': 'Logout realizado com sucesso'
        })
    except Exception as e:
        return Response({
            'error': f'Erro no logout: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def api_user_info(request):
    """
    Retorna informações do usuário autenticado
    """
    if request.user.is_authenticated:
        return Response({
            'authenticated': True,
            'user': {
                'id': request.user.pk,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'is_staff': request.user.is_staff,
                'is_superuser': request.user.is_superuser,
            }
        })
    else:
        return Response({
            'authenticated': False
        }, status=status.HTTP_401_UNAUTHORIZED)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def session_login(request):
    """
    Login usando sessões do Django para o frontend HTML
    """
    if request.method == 'GET':
        # Verificar se o usuário já está logado
        if request.user.is_authenticated:
            return JsonResponse({
                'authenticated': True,
                'user': {
                    'id': request.user.pk,
                    'username': request.user.username,
                    'email': request.user.email,
                }
            })
        else:
            return JsonResponse({'authenticated': False})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                return JsonResponse({
                    'error': 'Username e password são obrigatórios'
                }, status=400)
            
            user = authenticate(request, username=username, password=password)
            
            if user:
                if user.is_active:
                    login(request, user)
                    return JsonResponse({
                        'success': True,
                        'user': {
                            'id': user.pk,
                            'username': user.username,
                            'email': user.email,
                        }
                    })
                else:
                    return JsonResponse({
                        'error': 'Conta desativada'
                    }, status=401)
            else:
                return JsonResponse({
                    'error': 'Credenciais inválidas'
                }, status=401)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Erro interno: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def session_logout(request):
    """
    Logout usando sessões do Django
    """
    logout(request)
    return JsonResponse({'success': True, 'message': 'Logout realizado com sucesso'})


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    """
    Renovar token de acesso usando refresh token
    """
    try:
        refresh_token = request.data.get('refresh_token')
        
        if not refresh_token:
            return Response({
                'error': 'Refresh token é obrigatório'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        token = RefreshToken(refresh_token)
        new_access_token = token.access_token
        
        return Response({
            'access_token': str(new_access_token)
        })
        
    except Exception as e:
        return Response({
            'error': f'Token inválido: {str(e)}'
        }, status=status.HTTP_401_UNAUTHORIZED)
