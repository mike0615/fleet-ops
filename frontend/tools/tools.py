"""
Tools UI component for FleetOps frontend.
Displays available tools based on user permissions.
"""

import json

def render_tools_menu(available_tools):
    """
    Render tools menu HTML.

    Args:
        available_tools: List of available tool dicts

    Returns:
        HTML string
    """
    if not available_tools:
        return '<div class="alert alert-info">No tools available</div>'

    html = '<div class="tools-menu">'
    for tool in available_tools:
        html += f'''
            <a href="/tools/{tool['name']}/" class="tool-card">
                <div class="tool-icon">
                    <i class="fas fa-{tool['icon']}"></i>
                </div>
                <div class="tool-info">
                    <h4>{tool['display_name']}</h4>
                    <p>{tool['description']}</p>
                </div>
                <i class="fas fa-chevron-right tool-arrow"></i>
            </a>
        '''
    html += '</div>'
    return html


TOOLS_CSS = '''
<style>
    .tools-section {
        padding: 20px;
    }

    .tools-section h2 {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 20px;
        color: #333;
    }

    .tools-menu {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 20px;
        margin-bottom: 30px;
    }

    .tool-card {
        display: flex;
        align-items: center;
        padding: 20px;
        background: white;
        border-radius: 10px;
        border: 2px solid #f0f0f0;
        text-decoration: none;
        color: inherit;
        transition: all 0.3s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }

    .tool-card:hover {
        border-color: #667eea;
        box-shadow: 0 4px 16px rgba(102, 126, 234, 0.15);
        transform: translateY(-2px);
    }

    .tool-icon {
        width: 60px;
        height: 60px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 28px;
        margin-right: 20px;
        flex-shrink: 0;
    }

    .tool-info {
        flex: 1;
    }

    .tool-info h4 {
        font-size: 16px;
        font-weight: 700;
        color: #333;
        margin-bottom: 5px;
    }

    .tool-info p {
        font-size: 13px;
        color: #666;
        margin: 0;
    }

    .tool-arrow {
        color: #ddd;
        margin-left: 10px;
        transition: color 0.3s ease;
    }

    .tool-card:hover .tool-arrow {
        color: #667eea;
    }

    .tools-links {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
    }

    .tool-link-btn {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 10px 16px;
        background: #f5f5f5;
        border: 1px solid #ddd;
        border-radius: 6px;
        text-decoration: none;
        color: #333;
        transition: all 0.3s ease;
        font-size: 14px;
    }

    .tool-link-btn:hover {
        background: #667eea;
        color: white;
        border-color: #667eea;
    }
</style>
'''


def render_tools_section(user_permissions=None):
    """
    Render full tools section.

    Args:
        user_permissions: List of user permissions

    Returns:
        HTML string
    """
    # This would be called from the main app
    # For now, return the CSS
    return TOOLS_CSS
