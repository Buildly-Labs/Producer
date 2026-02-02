from django.http import HttpResponse

def health_check(request):
    return HttpResponse("Service is healthy", content_type="text/plain")