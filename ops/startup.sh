#!/bin/bash
#
# Producer Service Management Script
# Usage: ./ops/startup.sh [start|stop|restart|status|setup]
#
# This script manages the Producer Django application:
#   - Creates/activates virtualenv if needed
#   - Installs/updates requirements
#   - Starts, stops, or restarts the application
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="${PROJECT_ROOT}/venv"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
REQUIREMENTS_DEV_FILE="${PROJECT_ROOT}/requirements-dev.txt"
PID_FILE="${PROJECT_ROOT}/.django.pid"
PORT_FILE="${PROJECT_ROOT}/.django.port"
LOG_FILE="${PROJECT_ROOT}/logs/django.log"
HOST="${HOST:-0.0.0.0}"
PORT_RANGE_START=8000
PORT_RANGE_END=8010
PYTHON_VERSION="${PYTHON_VERSION:-python3}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if a port is in use
is_port_in_use() {
    local port=$1
    if command -v lsof &> /dev/null; then
        lsof -i :"$port" &> /dev/null
        return $?
    elif command -v nc &> /dev/null; then
        nc -z localhost "$port" &> /dev/null
        return $?
    else
        # Fallback: try to connect with /dev/tcp (bash only)
        (echo >/dev/tcp/localhost/"$port") &>/dev/null
        return $?
    fi
}

# Find an available port in the configured range
find_available_port() {
    # If PORT env var is explicitly set, use it
    if [ -n "${PORT:-}" ]; then
        echo "$PORT"
        return 0
    fi
    
    # Check if we have a saved port from a previous run that's still available
    if [ -f "$PORT_FILE" ]; then
        local saved_port=$(cat "$PORT_FILE")
        if ! is_port_in_use "$saved_port"; then
            echo "$saved_port"
            return 0
        fi
    fi
    
    # Find first available port in range
    for port in $(seq $PORT_RANGE_START $PORT_RANGE_END); do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done
    
    log_error "No available ports found in range ${PORT_RANGE_START}-${PORT_RANGE_END}"
    return 1
}

# Ensure we're in the project root
cd "$PROJECT_ROOT"

# Create logs directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Check if virtualenv exists, create if not
ensure_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating virtual environment at ${VENV_DIR}..."
        $PYTHON_VERSION -m venv "$VENV_DIR"
        log_success "Virtual environment created."
    else
        log_info "Virtual environment already exists."
    fi
}

# Activate virtualenv
activate_venv() {
    if [ -f "${VENV_DIR}/bin/activate" ]; then
        source "${VENV_DIR}/bin/activate"
        log_info "Virtual environment activated."
    else
        log_error "Virtual environment not found. Run 'setup' first."
        exit 1
    fi
}

# Install or update requirements
install_requirements() {
    activate_venv
    
    # Upgrade pip first
    log_info "Upgrading pip..."
    pip install --upgrade pip -q
    
    # Check if requirements need updating by comparing checksums
    REQUIREMENTS_HASH_FILE="${VENV_DIR}/.requirements_hash"
    CURRENT_HASH=$(md5sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || md5 -q "$REQUIREMENTS_FILE" 2>/dev/null)
    STORED_HASH=""
    
    if [ -f "$REQUIREMENTS_HASH_FILE" ]; then
        STORED_HASH=$(cat "$REQUIREMENTS_HASH_FILE")
    fi
    
    if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
        log_info "Installing/updating requirements from ${REQUIREMENTS_FILE}..."
        pip install -r "$REQUIREMENTS_FILE"
        echo "$CURRENT_HASH" > "$REQUIREMENTS_HASH_FILE"
        log_success "Requirements installed/updated."
    else
        log_info "Requirements are up to date."
    fi
    
    # Check for dev requirements if they exist
    if [ -f "$REQUIREMENTS_DEV_FILE" ]; then
        DEV_HASH_FILE="${VENV_DIR}/.requirements_dev_hash"
        DEV_CURRENT_HASH=$(md5sum "$REQUIREMENTS_DEV_FILE" 2>/dev/null | cut -d' ' -f1 || md5 -q "$REQUIREMENTS_DEV_FILE" 2>/dev/null)
        DEV_STORED_HASH=""
        
        if [ -f "$DEV_HASH_FILE" ]; then
            DEV_STORED_HASH=$(cat "$DEV_HASH_FILE")
        fi
        
        if [ "$DEV_CURRENT_HASH" != "$DEV_STORED_HASH" ]; then
            log_info "Installing/updating dev requirements..."
            pip install -r "$REQUIREMENTS_DEV_FILE"
            echo "$DEV_CURRENT_HASH" > "$DEV_HASH_FILE"
            log_success "Dev requirements installed/updated."
        fi
    fi
}

# Run database migrations
run_migrations() {
    activate_venv
    log_info "Running database migrations..."
    python manage.py migrate --noinput
    log_success "Migrations complete."
}

# Collect static files
collect_static() {
    activate_venv
    log_info "Collecting static files..."
    python manage.py collectstatic --noinput -q
    log_success "Static files collected."
}

# Get the PID of the running server
get_pid() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "$PID"
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    echo ""
    return 1
}

# Check if server is running
is_running() {
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        return 0
    fi
    return 1
}

# Start the application
start_app() {
    if is_running; then
        log_warn "Application is already running (PID: $(get_pid))"
        return 0
    fi
    
    ensure_venv
    install_requirements
    activate_venv
    
    # Run migrations if needed
    run_migrations
    
    # Find an available port
    PORT=$(find_available_port)
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    log_info "Starting Django development server on ${HOST}:${PORT}..."
    
    # Start in background and save PID
    nohup python manage.py runserver "${HOST}:${PORT}" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "$PORT" > "$PORT_FILE"
    
    sleep 2
    
    if is_running; then
        log_success "Application started (PID: $(get_pid))"
        log_info "Logs: ${LOG_FILE}"
        log_info "Access: http://${HOST}:${PORT}/"
    else
        log_error "Failed to start application. Check logs: ${LOG_FILE}"
        exit 1
    fi
}

# Start with Gunicorn (production)
start_production() {
    if is_running; then
        log_warn "Application is already running (PID: $(get_pid))"
        return 0
    fi
    
    ensure_venv
    install_requirements
    activate_venv
    
    run_migrations
    collect_static
    
    # Find an available port
    PORT=$(find_available_port)
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    log_info "Starting Gunicorn on ${HOST}:${PORT}..."
    
    WORKERS="${GUNICORN_WORKERS:-4}"
    
    nohup gunicorn logic_service.wsgi:application \
        --bind "${HOST}:${PORT}" \
        --workers "$WORKERS" \
        --access-logfile "${PROJECT_ROOT}/logs/access.log" \
        --error-logfile "${PROJECT_ROOT}/logs/error.log" \
        --pid "$PID_FILE" \
        --daemon
    
    echo "$PORT" > "$PORT_FILE"
    
    sleep 2
    
    if is_running; then
        log_success "Gunicorn started (PID: $(get_pid))"
        log_info "Access: http://${HOST}:${PORT}/"
    else
        log_error "Failed to start Gunicorn. Check logs."
        exit 1
    fi
}

# Stop the application
stop_app() {
    if ! is_running; then
        log_warn "Application is not running."
        return 0
    fi
    
    PID=$(get_pid)
    log_info "Stopping application (PID: ${PID})..."
    
    kill "$PID" 2>/dev/null || true
    
    # Wait for process to stop
    for i in {1..10}; do
        if ! is_running; then
            rm -f "$PID_FILE"
            log_success "Application stopped."
            return 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    log_warn "Forcing shutdown..."
    kill -9 "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
    log_success "Application stopped (forced)."
}

# Restart the application
restart_app() {
    log_info "Restarting application..."
    stop_app
    sleep 2
    start_app
}

# Show application status
show_status() {
    if is_running; then
        PID=$(get_pid)
        CURRENT_PORT=""
        if [ -f "$PORT_FILE" ]; then
            CURRENT_PORT=$(cat "$PORT_FILE")
        fi
        log_success "Application is running (PID: ${PID})"
        if [ -n "$CURRENT_PORT" ]; then
            log_info "Server: http://${HOST}:${CURRENT_PORT}/"
        fi
        echo ""
        echo "Process details:"
        ps -p "$PID" -o pid,ppid,user,%cpu,%mem,start,time,command 2>/dev/null || true
    else
        log_warn "Application is not running."
    fi
}

# Setup environment (first-time setup)
setup_env() {
    log_info "Setting up development environment..."
    
    ensure_venv
    install_requirements
    activate_venv
    
    # Create .env file if it doesn't exist
    if [ ! -f "${PROJECT_ROOT}/.env" ]; then
        log_info "Creating .env file from template..."
        cat > "${PROJECT_ROOT}/.env" << 'EOF'
# Database Configuration
DATABASE_ENGINE=postgresql
DATABASE_NAME=producer_db
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_HOST=localhost
DATABASE_PORT=5432

# Django Settings
DEBUG=True
SECRET_KEY=change-me-in-production

# AI Provider (mock for development)
AI_PROVIDER=mock
EOF
        log_warn "Created .env file - please update with your settings!"
    fi
    
    # Run migrations
    run_migrations
    
    log_success "Setup complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Update .env with your database credentials"
    echo "  2. Run: ./ops/startup.sh start"
    echo "  3. Access: http://localhost:8000/ledger/"
}

# Show usage information
show_usage() {
    echo "Producer Service Management Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start       Start the development server"
    echo "  stop        Stop the running server"
    echo "  restart     Restart the server"
    echo "  status      Show server status"
    echo "  setup       First-time setup (venv, requirements, migrations)"
    echo "  production  Start with Gunicorn (production mode)"
    echo "  logs        Tail the application logs"
    echo "  shell       Open Django shell"
    echo "  test        Run tests"
    echo "  migrate     Run database migrations"
    echo ""
    echo "Environment Variables:"
    echo "  HOST              Server host (default: 0.0.0.0)"
    echo "  PORT              Server port (default: 8000)"
    echo "  PYTHON_VERSION    Python executable (default: python3)"
    echo "  GUNICORN_WORKERS  Number of Gunicorn workers (default: 4)"
    echo ""
    echo "Examples:"
    echo "  $0 setup          # First-time setup"
    echo "  $0 start          # Start development server"
    echo "  PORT=8080 $0 start  # Start on custom port"
    echo "  $0 production     # Start production server"
}

# Tail logs
tail_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        log_warn "No log file found at ${LOG_FILE}"
    fi
}

# Open Django shell
django_shell() {
    activate_venv
    python manage.py shell
}

# Run tests
run_tests() {
    activate_venv
    log_info "Running tests..."
    python manage.py test "$@"
}

# Main command handler
case "${1:-}" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        restart_app
        ;;
    status)
        show_status
        ;;
    setup)
        setup_env
        ;;
    production|prod)
        start_production
        ;;
    logs)
        tail_logs
        ;;
    shell)
        django_shell
        ;;
    test)
        shift
        run_tests "$@"
        ;;
    migrate)
        activate_venv
        run_migrations
        ;;
    *)
        show_usage
        ;;
esac
