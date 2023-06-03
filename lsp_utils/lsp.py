# Copyright (C) 2017-2020 ycmd contributors
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

import os
import json
from collections.abc import Mapping
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import pathname2url, url2pathname

def ToBytes(value):
    if not value:
        return b''

    if type(value) == bytes:
        return value

    if isinstance(value, str):
        return value.encode('utf-8')

    return str(value).encode('utf-8')

def ToUnicode( value ):
  if not value:
    return ''
  if isinstance( value, str ):
    return value
  if isinstance( value, bytes ):
    # All incoming text should be utf8
    return str( value, 'utf8' )
  return str( value )

def UpdateDict(target, override):

    for key, value in override.items():
        current_value = target.get(key)
        if not isinstance(current_value, Mapping):
            target[key] = value
        elif isinstance(value, Mapping):
            target[key] = UpdateDict(current_value, value)
        else:
            target[key] = value

    return target


def FilePathToUri(file_name):
    return urljoin('file:', pathname2url(file_name))


SYMBOL_KIND_STR_LIST = [
    None,
    'File',
    'Module',
    'Namespace',
    'Package',
    'Class',
    'Method',
    'Property',
    'Field',
    'Constructor',
    'Enum',
    'Interface',
    'Function',
    'Variable',
    'Constant',
    'String',
    'Number',
    'Boolean',
    'Array',
    'Object',
    'Key',
    'Null',
    'EnumMember',
    'Struct',
    'Event',
    'Operator',
    'TypeParameter',
]


TOKEN_TYPES_STR_LIST = [
  'namespace',
  'type',
  'class',
  'enum',
  'interface',
  'struct',
  'typeParameter',
  'parameter',
  'variable',
  'property',
  'enumMember',
  'event',
  'function',
  'method',
  'member',
  'macro',
  'keyword',
  'modifier',
  'comment',
  'string',
  'number',
  'regexp',
  'operator',
]

TOKEN_MODIFIERS = []


def Initialize(request_id, project_directory, extra_capabilities = {}, settings = {}):
    capabilities = {
        'textDocument': {
            'documentSymbol': {
                'symbolKind': {
                    'valueSet': list(range(1, len(SYMBOL_KIND_STR_LIST))),
                },
                'hierarchicalDocumentSymbolSupport': True,
                'labelSupport': False,
            },
        },
    }
    return BuildRequest(request_id, 'initialize', {
        'processId': os.getpid(),
        'rootPath': project_directory,
        'rootUri': FilePathToUri(project_directory),
        'initializationOptions': settings,
        'capabilities': UpdateDict(capabilities, extra_capabilities),
        'workspaceFolders': None,
    })


# def Initialize( request_id, project_directory, extra_capabilities, settings ):
#   """Build the Language Server initialize request"""

#   capabilities = {
#     'workspace': {
#       'applyEdit': True,
#       'didChangeWatchedFiles': {
#         'dynamicRegistration': True
#       },
#       'workspaceEdit': { 'documentChanges': True, },
#       'symbol': {
#         'symbolKind': {
#           'valueSet': list( range( 1, len( SYMBOL_KIND_STR_LIST ) ) ),
#         }
#       },
#       'workspaceFolders': True,
#     },
#     'textDocument': {
#       'codeAction': {
#         'codeActionLiteralSupport': {
#           'codeActionKind': {
#             'valueSet': [ '',
#                           'quickfix',
#                           'refactor',
#                           'refactor.extract',
#                           'refactor.inline',
#                           'refactor.rewrite',
#                           'source',
#                           'source.organizeImports' ]
#           }
#         }
#       },
#       'documentSymbol': {
#         'symbolKind': {
#           'valueSet': list( range( 1, len( SYMBOL_KIND_STR_LIST ) ) ),
#         },
#         'hierarchicalDocumentSymbolSupport': False,
#         'labelSupport': False,
#       },
#       'hover': {
#         'contentFormat': [
#           'plaintext',
#           'markdown'
#         ]
#       },
#       'signatureHelp': {
#         'signatureInformation': {
#           'parameterInformation': {
#             'labelOffsetSupport': True,
#           },
#           'documentationFormat': [
#             'plaintext',
#             'markdown'
#           ],
#         },
#       },
#       'semanticTokens': {
#         'requests': {
#           'range': True,
#           'full': {
#             'delta': False
#           }
#         },
#         'tokenTypes': TOKEN_TYPES_STR_LIST,
#         'tokenModifiers': TOKEN_MODIFIERS,
#         'formats': [ 'relative' ],
#         'augmentSyntaxTokens': True,
#       },
#       'synchronization': {
#         'didSave': True
#       },
#       'inlay_hint': {
#       }
#     },
#   }
#   return BuildRequest( request_id, 'initialize', {
#     'processId': os.getpid(),
#     'rootPath': project_directory,
#     'rootUri': FilePathToUri( project_directory ),
#     'initializationOptions': settings,
#     'capabilities': UpdateDict( capabilities, extra_capabilities ),
#     'workspaceFolders': WorkspaceFolders( project_directory ),
#   } )


def WorkspaceFolders( *args ):
  return [
    {
      'uri': FilePathToUri( f ),
      'name': os.path.basename( f )
    } for f in args
  ]

def DidOpenTextDocument(file_path, file_types, file_contents):
    return BuildNotification('textDocument/didOpen', {
        'textDocument': {
            'uri': FilePathToUri(file_path),
            'languageId': '/'.join(file_types),
            'version': 1,
            'text': file_contents
        }
    })

def DocumentSymbol( request_id, file_path ):
  return BuildRequest( request_id, 'textDocument/documentSymbol', {
    'textDocument': {
      'uri': FilePathToUri( file_path ),
    },
  } )


def BuildRequest(request_id, method, parameters):
    return _BuildMessageData({
        'id': request_id,
        'method': method,
        'params': parameters,
    })


def BuildNotification(method, parameters):
    return _BuildMessageData({
        'method': method,
        'params': parameters,
    })


def _BuildMessageData(message):
    message['jsonrpc'] = '2.0'
    request = json.dumps(message, separators=(',', ':'), sort_keys=True)

    packet = ToBytes(request)
    packet = ToBytes(f'Content-Length: { len( packet ) }\r\n\r\n') + packet
    return packet


class SymbolKind:
    File = 1
    Module = 2
    Namespace = 3
    Package = 4
    Class = 5
    Method = 6
    Property = 7
    Field = 8
    Constructor = 9
    Enum = 10
    Interface = 11
    Function = 12
    Variable = 13
    Constant = 14
    String = 15
    Number = 16
    Boolean = 17
    Array = 18
    Object = 19
    Key = 20
    Null = 21
    EnumMember = 22
    Struct = 23
    Event = 24
    Operator = 25
    TypeParameter = 26
