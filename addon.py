﻿# coding=utf-8
import os, sys, shutil, unicodedata, re, types
from htmlentitydefs import name2codepoint
import xbmc, xbmcaddon, xbmcplugin, xbmcgui, xbmcvfs
import xml.etree.ElementTree as xmltree
import urllib
from unidecode import unidecode
from urlparse import parse_qs
from traceback import print_exc

if sys.version_info < (2, 7):
    import simplejson
else:
    import json as simplejson

__addon__        = xbmcaddon.Addon()
__addonid__      = __addon__.getAddonInfo('id').decode( 'utf-8' )
__addonversion__ = __addon__.getAddonInfo('version')
__language__     = __addon__.getLocalizedString
__cwd__          = __addon__.getAddonInfo('path').decode("utf-8")
__addonname__    = __addon__.getAddonInfo('name').decode("utf-8")
__resource__     = xbmc.translatePath( os.path.join( __cwd__, 'resources', 'lib' ) ).decode("utf-8")
__datapath__     = os.path.join( xbmc.translatePath( "special://profile/" ).decode( 'utf-8' ), "addon_data", __addonid__ )

sys.path.append(__resource__)

import rules, viewattrib, orderby
RULE = rules.RuleFunctions()
ATTRIB = viewattrib.ViewAttribFunctions()
ORDERBY = orderby.OrderByFunctions()

# character entity reference
CHAR_ENTITY_REXP = re.compile('&(%s);' % '|'.join(name2codepoint))

# decimal character reference
DECIMAL_REXP = re.compile('&#(\d+);')

# hexadecimal character reference
HEX_REXP = re.compile('&#x([\da-fA-F]+);')

REPLACE1_REXP = re.compile(r'[\']+')
REPLACE2_REXP = re.compile(r'[^-a-z0-9]+')
REMOVE_REXP = re.compile('-{2,}')

def log(txt):

    if isinstance (txt,str):
        txt = txt.decode('utf-8')
    message = u'%s: %s' % (__addonid__, txt)
    xbmc.log(msg=message.encode('utf-8'), level=xbmc.LOGDEBUG)
        
class Main:
    # MAIN ENTRY POINT
    def __init__(self):
        self._parse_argv()
        
        # If there are no custom video nodes in the profile directory, copy them from the XBMC install
        targetDir = os.path.join( xbmc.translatePath( "special://profile".decode('utf-8') ), "library", "video" )
        try:
            if not os.path.exists( targetDir ):
                xbmcvfs.mkdirs( targetDir )
                originDir = os.path.join( xbmc.translatePath( "special://xbmc".decode( "utf-8" ) ), "system", "library", "video" )
                dirs, files = xbmcvfs.listdir( originDir )
                self.copyNode( dirs, files, targetDir, originDir )
        except:
            xbmcgui.Dialog().ok(__addonname__, __language__( 30400 ) )
            print_exc
            xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))
            return
            
        # Create data if not exists
        if not os.path.exists(__datapath__):
            xbmcvfs.mkdir(__datapath__)
            
        if "type" in self.PARAMS:
            # We're performing a specific action
            if self.PARAMS[ "type" ] == "delete":
                message = __language__( 30401 )
                if self.PARAMS[ "actionPath" ] == targetDir:
                    # Ask the user is they want to reset all nodes
                    message = __language__( 30402 )
                result = xbmcgui.Dialog().yesno(__addonname__, message )
                if result:
                    if self.PARAMS[ "actionPath" ].endswith( ".xml" ):
                        # Delete single file
                        xbmcvfs.delete( self.PARAMS[ "actionPath" ] )
                    else:
                        # Delete folder
                        RULE.deleteAllNodeRules( self.PARAMS[ "actionPath" ] )
                        shutil.rmtree( self.PARAMS[ "actionPath" ] )
                        
            if self.PARAMS[ "type" ] == "deletenode":
                result = xbmcgui.Dialog().yesno(__addonname__, __language__( 30403 ) )
                if result:
                    self.changeViewElement( self.PARAMS[ "actionPath" ], self.PARAMS[ "node" ], "" ) 
                        
            if self.PARAMS[ "type" ] == "editlabel":

                if self.PARAMS[ "label" ].isdigit():
                    label = xbmc.getLocalizedString( int( self.PARAMS[ "label" ] ) )
                else:
                    label = self.PARAMS[ "label" ]
                    
                # Get new label from keyboard dialog
                keyboard = xbmc.Keyboard( label, __language__( 30300 ), False )
                keyboard.doModal()
                if ( keyboard.isConfirmed() ):
                    newlabel = keyboard.getText().decode( "utf-8" )
                    if newlabel != "" and newlabel != label:
                        # We've got a new label, update the xml file
                        self.changeViewElement( self.PARAMS[ "actionPath" ], "label", newlabel )
                        
            if self.PARAMS[ "type" ] == "editvisibility":
                currentVisibility = self.getRootAttrib( self.PARAMS[ "actionPath" ], "visible" )
                    
                # Get new visibility from keyboard dialog
                keyboard = xbmc.Keyboard( currentVisibility, __language__( 30301 ), False )
                keyboard.doModal()
                if ( keyboard.isConfirmed() ):
                    newVisibility = keyboard.getText()
                    if newVisibility != currentVisibility:
                        # We've got a new label, update the xml file
                        self.changeRootAttrib( self.PARAMS[ "actionPath" ], "visible", newVisibility )
                        
            if self.PARAMS[ "type" ] == "editorder":
                currentOrder = self.getRootAttrib( self.PARAMS[ "actionPath" ], "order" )
                    
                # Get new label from keyboard dialog
                neworder = xbmcgui.Dialog().numeric( 0, __language__( 30302 ), currentOrder )
                if neworder != "" and neworder != currentOrder:
                    # We've got a new label, update the xml file
                    self.changeRootAttrib( self.PARAMS[ "actionPath" ], "order", neworder )
                    
            if self.PARAMS[ "type" ] == "newView":
                # Get new view name from keyboard dialog
                keyboard = xbmc.Keyboard( "", __language__( 30316 ), False )
                keyboard.doModal()
                if ( keyboard.isConfirmed() ):
                    newView = keyboard.getText().decode( "utf-8" )
                    if newView != "":
                        # Ensure filename is unique
                        filename = self.slugify( newView.lower().replace( " ", "" ) )
                        if os.path.exists( os.path.join( self.PARAMS[ "actionPath" ], filename + ".xml" ) ):
                            count = 0
                            while os.path.exists( os.path.join( self.PARAMS[ "actionPath" ], filename + "-" + str( count ) + ".xml" ) ):
                                count += 1
                            filename = filename + "-" + str( count )
                        
                        # Create a new xml file
                        tree = xmltree.ElementTree( xmltree.Element( "node" ) )
                        root = tree.getroot()
                        subtree = xmltree.SubElement( root, "label" ).text = newView
                        
                        # Add any node rules
                        RULE.addAllNodeRules( self.PARAMS[ "actionPath" ], root )
                        
                        # Write the xml file
                        self.indent( root )
                        tree.write( os.path.join( self.PARAMS[ "actionPath" ], filename + ".xml" ), encoding="UTF-8" )
                        
            if self.PARAMS[ "type" ] == "newNode":
                # Get new node name from the keyboard dialog
                keyboard = xbmc.Keyboard( "", __language__( 30303 ), False )
                keyboard.doModal()
                if ( keyboard.isConfirmed() ):
                    newNode = keyboard.getText().decode( "utf8" )
                    if newNode == "":
                        return
                        
                    # Ensure foldername is unique
                    foldername = self.slugify( newNode.lower().replace( " ", "" ) )
                    if os.path.exists( os.path.join( self.PARAMS[ "actionPath" ], foldername + os.pathsep ) ):
                        count = 0
                        while os.path.exists( os.path.join( self.PARAMS[ "actionPath" ], foldername + "-" + str( count ) + os.pathsep ) ):
                            count += 1
                        foldername = foldername + "-" + str( count )
                    foldername = os.path.join( self.PARAMS[ "actionPath" ], foldername )
                        
                    # Create new node folder
                    xbmcvfs.mkdir( foldername )
                    
                    # Create a new xml file
                    tree = xmltree.ElementTree( xmltree.Element( "node" ) )
                    root = tree.getroot()
                    subtree = xmltree.SubElement( root, "label" ).text = newNode
                    
                    # Ask user if they want to import defaults
                    defaultNames = [ xbmc.getLocalizedString( 231 ), xbmc.getLocalizedString( 342 ), xbmc.getLocalizedString( 20343 ), xbmc.getLocalizedString( 20389 ) ]
                    defaultValues = [ "", "movies", "tvshows", "musicvideos" ]
                    
                    selected = xbmcgui.Dialog().select( __language__( 30304 ), defaultNames )
                    
                    # If the user selected some defaults...
                    if selected != -1 and selected != 0:
                        try:
                            # Copy those defaults across
                            originDir = os.path.join( xbmc.translatePath( "special://xbmc".decode( "utf-8" ) ), "system", "library", "video", defaultValues[ selected ] )
                            dirs, files = xbmcvfs.listdir( originDir )
                            for file in files:
                                if file != "index.xml":
                                    xbmcvfs.copy( os.path.join( originDir, file), os.path.join( foldername, file ) )
                                        
                            # Open index.xml and copy values across
                            index = xmltree.parse( os.path.join( originDir, "index.xml" ) ).getroot()
                            if "visible" in index.attrib:
                                root.set( "visible", index.attrib.get( "visible" ) )
                            icon = index.find( "icon" )
                            if icon is not None:
                                xmltree.SubElement( root, "icon" ).text = icon.text
                            
                        except:
                            print_exc()
                        
                    # Write the xml file
                    self.indent( root )
                    tree.write( os.path.join( foldername, "index.xml" ), encoding="UTF-8" )

            if self.PARAMS[ "type" ] == "rule":
                # Display list of all elements of a rule
                RULE.displayRule( self.PARAMS[ "actionPath" ], self.PATH, self.PARAMS[ "rule" ] )
                return
                    
            if self.PARAMS[ "type" ] == "editMatch":
                # Editing the field the rule is matched against
                RULE.editMatch( self.PARAMS[ "actionPath" ], self.PARAMS[ "rule" ], self.PARAMS[ "content"], self.PARAMS[ "default" ] )
            if self.PARAMS[ "type" ] == "editOperator":
                # Editing the operator of a rule
                RULE.editOperator( self.PARAMS[ "actionPath" ], self.PARAMS[ "rule" ], self.PARAMS[ "group" ], self.PARAMS[ "default" ] )
            if self.PARAMS[ "type" ] == "editValue":
                # Editing the value of a rule
                RULE.editValue( self.PARAMS[ "actionPath" ], self.PARAMS[ "rule" ] )
            if self.PARAMS[ "type" ] == "browseValue":
                # Browse for the new value of a rule
                RULE.browse( self.PARAMS[ "actionPath" ], self.PARAMS[ "rule" ], self.PARAMS[ "match" ], self.PARAMS[ "content" ] )
                
            if self.PARAMS[ "type" ] == "deleteRule":
                # Delete a rule
                RULE.deleteRule( self.PARAMS[ "actionPath" ], self.PARAMS[ "rule" ] )
                
            # --- Edit order-by ---
            if self.PARAMS[ "type" ] == "orderby":
                # Display all elements of order by
                ORDERBY.displayOrderBy( self.PARAMS[ "actionPath" ] )
                return
                
            if self.PARAMS[ "type" ] == "editOrderBy":
                ORDERBY.editOrderBy( self.PARAMS[ "actionPath" ], self.PARAMS[ "content" ], self.PARAMS[ "default" ] )
            if self.PARAMS[ "type" ] == "editOrderByDirection":
                ORDERBY.editDirection( self.PARAMS[ "actionPath" ], self.PARAMS[ "default" ] )
                
            # --- Edit other attribute of view ---
            #  > Content
            if self.PARAMS[ "type" ] == "editContent":
                ATTRIB.editContent( self.PARAMS[ "actionPath" ], "" ) # No default to pass, yet!
                
            #  > Grouping
            if self.PARAMS[ "type" ] == "editGroup":
                ATTRIB.editGroup( self.PARAMS[ "actionPath" ], self.PARAMS[ "content" ], "" )

            #  > Limit
            if self.PARAMS[ "type" ] == "editLimit":
                ATTRIB.editLimit( self.PARAMS[ "actionPath" ], self.PARAMS[ "value" ] )
                
            #  > Path
            if self.PARAMS[ "type" ] == "addPath":
                ATTRIB.addPath( self.PARAMS[ "actionPath" ] )
            if self.PARAMS[ "type" ] == "editPath":
                ATTRIB.editPath( self.PARAMS[ "actionPath" ], self.PARAMS[ "value" ] )
                
            #  > Icon (also for node)
            if self.PARAMS[ "type" ] == "editIcon":
                ATTRIB.editIcon( self.PARAMS[ "actionPath" ], self.PARAMS[ "value" ] )
            if self.PARAMS[ "type" ] == "browseIcon":
                ATTRIB.browseIcon( self.PARAMS[ "actionPath" ] )
            
            # Refresh the listings and exit
            xbmc.executebuiltin("Container.Refresh")
            return
            
        if self.PATH.endswith( ".xml" ):
            # List rules for specific view
            rules, nextRule = self.getRules( self.PATH )
            hasContent = False
            content = ""
            hasOrder = False
            hasGroup = False
            hasLimit = False
            hasPath = False
            rulecount = 0
            self.PATH = self.PATH
            if rules is not None:
                for rule in rules:
                    commands = []
                    
                    if rule[ 0 ] == "content":
                        # 1 = Content
                        listitem = xbmcgui.ListItem( label="%s: %s" % ( __language__(30200), ATTRIB.translateContent( rule[ 1 ] ) ) )
                        commands.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deletenode&actionPath=" + self.PATH + "&node=content)" ) )
                        action = "plugin://plugin.program.video.node.editor?type=editContent&actionPath=" + self.PATH
                        hasContent = True
                        content = rule[ 1 ]
                        
                    if rule[ 0 ] == "order":
                        # 1 = orderby
                        # 2 = direction (optional?)
                        if len( rule ) == 3:
                            translate = ORDERBY.translateOrderBy( [ rule[ 1 ], rule[ 2 ] ] )
                            listitem = xbmcgui.ListItem( label="%s: %s (%s)" % ( __language__(30201), translate[ 0 ][ 0 ], translate[ 1 ][ 0 ] ) )
                        else:
                            translate = ORDERBY.translateOrderBy( [ rule[ 1 ], "" ] )
                            listitem = xbmcgui.ListItem( label="%s: %s" % ( __language__(30201), translate[ 0 ][ 0 ] ) )
                        commands.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deletenode&actionPath=" + self.PATH + "&node=order)" ) )
                        action = "plugin://plugin.program.video.node.editor?type=orderby&actionPath=" + self.PATH
                        hasOrder = True
                        
                    elif rule[ 0 ] == "group":
                        # 1 = group
                        listitem = xbmcgui.ListItem( label="%s: %s" % ( __language__(30202), ATTRIB.translateGroup( rule[ 1 ] ) ) )
                        commands.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deletenode&actionPath=" + self.PATH + "&node=group)" ) )
                        action = "plugin://plugin.program.video.node.editor?type=editGroup&actionPath=" + self.PATH + "&value=" + rule[ 1 ] + "&content=" + content
                        hasGroup = True
                        
                    elif rule[ 0 ] == "limit":
                        # 1 = limit
                        listitem = xbmcgui.ListItem( label="%s: %s" % ( __language__(30203), rule[ 1 ] ) )
                        commands.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deletenode&actionPath=" + self.PATH + "&node=limit)" ) )
                        action = "plugin://plugin.program.video.node.editor?type=editLimit&actionPath=" + self.PATH + "&value=" + rule[ 1 ]
                        hasLimit = True
                        
                    elif rule[ 0 ] == "path":
                        # 1 = path
                        listitem = xbmcgui.ListItem( label="%s: %s" % ( __language__(30204), rule[ 1 ] ) )
                        commands.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deletenode&actionPath=" + self.PATH + "&node=path)" ) )
                        action = "plugin://plugin.program.video.node.editor?type=editPath&actionPath=" + self.PATH + "&value=" + rule[ 1 ]
                        hasPath = True
                        
                    elif rule[ 0 ] == "rule":
                        # 1 = field
                        # 2 = operator
                        # 3 = value (optional)
                        # 4 = ruleNum
                        
                        if len(rule) == 3:
                            translated = RULE.translateRule( [ rule[ 1 ], rule[ 2 ] ] )
                        else:
                            translated = RULE.translateRule( [ rule[ 1 ], rule[ 2 ], rule[ 3 ] ] )
                        
                        if translated[ 2 ][ 0 ] == "|NONE|":
                            listitem = xbmcgui.ListItem( label="%s: %s %s" % ( __language__(30205), translated[ 0 ][ 0 ], translated[ 1 ][ 0 ] ) )
                        else:
                            listitem = xbmcgui.ListItem( label="%s: %s %s %s" % ( __language__(30205), translated[ 0 ][ 0 ], translated[ 1 ][ 0 ], translated[ 2 ][ 1 ] ) )
                        commands.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deleteRule&actionPath=" + self.PATH + "&rule=" + str( rule[ 4 ] ) + ")" ) )
                        action = "plugin://plugin.program.video.node.editor?type=rule&actionPath=" + self.PATH + "&rule=" + str( rule[ 4 ] )
                        
                        rulecount += 1
                    
                    listitem.addContextMenuItems( commands, replaceItems = True )
                    if rule[ 0 ] == "rule" or rule[ 0 ] == "order":
                        xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), action, listitem, isFolder=True )
                    else:
                        xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), action, listitem, isFolder=False )
                
            if not hasContent and not hasPath:
                # Add content
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=editContent&actionPath=" + self.PATH, xbmcgui.ListItem( label=__language__(30000) ) )
            if not hasOrder and hasContent:
                # Add order
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=orderby&actionPath=" + self.PATH, xbmcgui.ListItem( label=__language__(30002) ), isFolder=True )
            if not hasGroup and hasContent:
                # Add group
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=editGroup&actionPath=" + self.PATH + "&content=" + content, xbmcgui.ListItem( label=__language__(30004) ) )              
            if not hasLimit and hasContent:
                # Add limit
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=editLimit&actionPath=" + self.PATH + "&value=25", xbmcgui.ListItem( label=__language__(30003) ) )            
            if not hasPath and not hasContent:
                # Add path
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=addPath&actionPath=" + self.PATH, xbmcgui.ListItem( label=__language__(30001) ) )
            if hasContent:
                # Add rule
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=rule&actionPath=" + self.PATH + "&rule=" + str( nextRule ), xbmcgui.ListItem( label=__language__(30005) ), isFolder = True )
                
        else:
            # List nodes and views
            nodes = {}
            self.indexCounter = -1
            if self.PATH != "":
                self.listNodes( self.PATH, nodes )
            else:
                self.listNodes( targetDir, nodes )
                
            self.PATH = urllib.quote( self.PATH )
            
            # Check whether we should show Add To Menu option
            showAddToMenu = False
            if xbmc.getCondVisibility( "Skin.HasSetting(SkinShortcuts-FullMenu)" ):
                showAddToMenu = True
            
            for key in nodes:
                # 0 = Label
                # 1 = Icon
                # 2 = Path
                # 3 = Type
                # 4 = Order
                
                # Localize the label
                if nodes[ key ][ 0 ].isdigit():
                    label = xbmc.getLocalizedString( int( nodes[ key ][ 0 ] ) )
                else:
                    label = nodes[ key ][ 0 ]
                
                # Create the listitem
                if nodes[ key ][ 3 ] == "folder":
                    listitem = xbmcgui.ListItem( label="(%s) %s >" % ( nodes[ key ][ 4 ], label ), label2=nodes[ key ][ 4 ], iconImage=nodes[ key ][ 1 ] )
                else:
                    listitem = xbmcgui.ListItem( label="(%s) %s" % ( nodes[ key ][ 4 ], label ), label2=nodes[ key ][ 4 ], iconImage=nodes[ key ][ 1 ] )

                
                # Add context menu items
                commands = []
                commandsNode = []
                commandsView = []
                
                commandsNode.append( ( __language__(30101), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editlabel&actionPath=" + os.path.join( nodes[ key ][ 2 ], "index.xml" ) + "&label=" + nodes[ key ][ 0 ] + ")" ) )
                commandsNode.append( ( __language__(30102), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editIcon&actionPath=" + os.path.join( nodes[ key ][ 2 ], "index.xml" ) + "&value=" + nodes[ key ][ 1 ] + ")" ) )
                commandsNode.append( ( __language__(30103), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=browseIcon&actionPath=" + os.path.join( nodes [ key ][ 2 ], "index.xml" ) + ")" ) )
                commandsNode.append( ( __language__(30104), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editorder&actionPath=" + os.path.join( nodes[ key ][ 2 ], "index.xml" ) + ")" ) )
                commandsNode.append( ( __language__(30105), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editvisibility&actionPath=" + os.path.join( nodes[ key ][ 2 ], "index.xml" ) + ")" ) )
                commandsNode.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=delete&actionPath=" + nodes[ key ][ 2 ] + ")" ) )
                
                if showAddToMenu:
                    commandsNode.append( ( __language__(30106), "XBMC.RunScript(script.skinshortcuts,type=addNode&options=" + urllib.unquote( nodes[ key ][ 2 ] ).replace( targetDir, "" ) + "|" + urllib.quote( label.encode( "utf-8" ) ) + "|" + urllib.quote( nodes[ key ][ 1 ].encode( "utf-8" ) ) + ")" ) )
                
                commandsView = []
                commandsView.append( ( __language__(30101), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editlabel&actionPath=" + nodes[ key ][ 2 ] + "&label=" + nodes[ key ][ 0 ] + ")" ) )
                commandsView.append( ( __language__(30102), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editIcon&actionPath=" + nodes[ key ][ 2 ] + "&value=" + nodes[ key ][ 1 ] + ")" ) )
                commandsView.append( ( __language__(30103), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=browseIcon&actionPath=" + nodes[ key ][ 2 ] + ")" ) )
                commandsView.append( ( __language__(30104), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editorder&actionPath=" + nodes[ key ][ 2 ] + ")" ) )
                commandsView.append( ( __language__(30105), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=editvisibility&actionPath=" + nodes[ key ][ 2 ] + ")" ) )
                commandsView.append( ( __language__(30100), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=delete&actionPath=" + nodes[ key ][ 2 ] + ")" ) )
                
                if nodes[ key ][ 3 ] == "folder":
                    listitem.addContextMenuItems( commandsNode, replaceItems = True )
                    xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), "plugin://plugin.program.video.node.editor/?path=" + nodes[ key ][ 2 ], listitem, isFolder=True )
                else:
                    listitem.addContextMenuItems( commandsView, replaceItems = True )
                    xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), "plugin://plugin.program.video.node.editor/?path=" + nodes[ key ][ 2 ], listitem, isFolder=True )
                    
            if self.PATH != "":
                # Get any rules from the index.xml
                rules, nextRule = self.getRules( os.path.join( urllib.unquote( self.PATH ), "index.xml" ), True )
                rulecount = 0
                if rules is not None:
                    for rule in rules:
                        commands = []
                        if rule[ 0 ] == "rule":
                            # 1 = field
                            # 2 = operator
                            # 3 = value (optional)
                            if len(rule) == 3:
                                translated = RULE.translateRule( [ rule[ 1 ], rule[ 2 ] ] )
                            else:
                                translated = RULE.translateRule( [ rule[ 1 ], rule[ 2 ], rule[ 3 ] ] )
                                
                            if len(translated) == 2:
                                listitem = xbmcgui.ListItem( label="%s: %s %s" % ( __language__(30205), translated[ 0 ][ 0 ], translated[ 1 ][ 0 ] ) )
                            else:
                                listitem = xbmcgui.ListItem( label="%s: %s %s %s" % ( __language__(30205), translated[ 0 ][ 0 ], translated[ 1 ][ 0 ], translated[ 2 ][ 1 ] ) )
                            commands.append( ( __language__( 30100 ), "XBMC.RunPlugin(plugin://plugin.program.video.node.editor?type=deleteRule&actionPath=" + os.path.join( self.PATH, "index.xml" ) + "&rule=" + str( rulecount ) + ")" ) )
                            action = "plugin://plugin.program.video.node.editor?type=rule&actionPath=" + os.path.join( self.PATH, "index.xml" ) + "&rule=" + str( rulecount )

                            rulecount += 1
                        
                        listitem.addContextMenuItems( commands, replaceItems = True )
                        if rule[ 0 ] == "rule" or rule[ 0 ] == "order":
                            xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), action, listitem, isFolder=True )
                        else:
                            xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), action, listitem, isFolder=False )
                        
                # New rule
                xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=rule&actionPath=" + os.path.join( self.PATH, "index.xml" ) + "&rule=" + str( nextRule), xbmcgui.ListItem( label=__language__(30005) ), isFolder=True )
            
            showReset = False
            if self.PATH == "":
                self.PATH = urllib.quote( targetDir )
                showReset = True
            
            # New view and node
            xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=newView&actionPath=" + self.PATH, xbmcgui.ListItem( label=__language__(30006) ) )
            xbmcplugin.addDirectoryItem( int( sys.argv[ 1 ] ), "plugin://plugin.program.video.node.editor?type=newNode&actionPath=" + self.PATH, xbmcgui.ListItem( label=__language__(30007) ) )
            
            if showReset:
                xbmcplugin.addDirectoryItem( int(sys.argv[ 1 ]), "plugin://plugin.program.video.node.editor/?type=delete&actionPath=" + targetDir, xbmcgui.ListItem( label=__language__(30008) ), isFolder=False )
        
        xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))
        
    def _parse_argv( self ):
        try:
            p = parse_qs(sys.argv[2][1:])
            for i in p.keys():
                p[i] = p[i][0].decode( "utf-8" )
            self.PARAMS = p
        except:
            p = parse_qs(sys.argv[1])
            for i in p.keys():
                p[i] = p[i][0].decode( "utf-8" )
            self.PARAMS = p
            
        if "path" in self.PARAMS:
            self.PATH = self.PARAMS[ "path" ]
        else:
            self.PATH = ""
        
    def getRules( self, actionPath, justRules = False ):
        returnVal = []
        try:
            # Load the xml file
            tree = xmltree.parse( actionPath )
            root = tree.getroot()
            
            if justRules == False:
                # Look for a 'content'
                content = root.find( "content" )
                if content is not None:
                    returnVal.append( ( "content", content.text.decode( "utf-8" ) ) )
                
                # Look for an 'order'
                order = root.find( "order" )
                if order is not None:
                    if "direction" in order.attrib:
                        returnVal.append( ( "order", order.text, order.attrib.get( "direction" ) ) )
                    else:
                        returnVal.append( ( "order", order.text ) )
                
                # Look for a 'group'
                group = root.find( "group" )
                if group is not None:
                    returnVal.append( ( "group", group.text ) )
                    
                # Look for a 'limit'
                limit = root.find( "limit" )
                if limit is not None:
                    returnVal.append( ( "limit", limit.text ) )
                    
                # Look for a 'path'
                path = root.find( "path" )
                if path is not None:
                    returnVal.append( ( "path", path.text ) )
                
            ruleNum = 0
            
            # Look for any rules
            if actionPath.endswith( "index.xml" ):
                # Load the rules from RULE module
                rules = RULE.getNodeRules( actionPath )
                if rules is not None:
                    for rule in rules:
                        returnVal.append( ( "rule", rule[ 0 ], rule[ 1 ], rule[ 2 ], ruleNum ) )
                        ruleNum += 1
                    return returnVal, len( rules )
                else:
                    return returnVal, 0
            else:
                rules = root.findall( "rule" )
                
                # Process the rules
                if rules is not None:
                    for rule in rules:
                        value = rule.find( "value" )
                        if value is not None and value.text is not None:
                            translated = RULE.translateRule( [ rule.attrib.get( "field" ), rule.attrib.get( "operator" ), value.text ] )
                            if not RULE.isNodeRule( translated, actionPath ):
                                returnVal.append( ( "rule", rule.attrib.get( "field" ), rule.attrib.get( "operator" ), value.text, ruleNum ) )
                        else:
                            translated = RULE.translateRule( [ rule.attrib.get( "field" ), rule.attrib.get( "operator" ), "" ] )
                            if not RULE.isNodeRule( translated, actionPath ):
                                returnVal.append( ( "rule", rule.attrib.get( "field" ), rule.attrib.get( "operator" ), "", ruleNum ) )
                        ruleNum += 1
                    
                    return returnVal, len( rules )
                
            return returnVal, 0
        except:
            print_exc()
        
    def listNodes( self, targetDir, nodes ):
        dirs, files = xbmcvfs.listdir( targetDir )
        for dir in dirs:
            self.parseNode( os.path.join( targetDir, dir ), nodes )
        for file in files:
            self.parseItem( os.path.join( targetDir, file.decode( "utf-8" ) ), nodes )
        
    def parseNode( self, node, nodes ):
        # If the folder we've been passed contains an index.xml, send that file to be processed
        if os.path.exists( os.path.join( node, "index.xml" ) ):
        
            # BETA2 ONLY CODE
            RULE.moveNodeRuleToAppdata( node, os.path.join( node, "index.xml" ) )
            # /BETA2 ONLY CODE
            
            self.parseItem( os.path.join( node, "index.xml" ), nodes, True, node )
    
    def parseItem( self, file, nodes, isFolder = False, origFolder = None ):
        if not isFolder and file.endswith( "index.xml" ):
            return
        try:
            # Load the xml file
            tree = xmltree.parse( file )
            root = tree.getroot()
            
            # Get the item index
            if "order" in tree.getroot().attrib:
                index = tree.getroot().attrib.get( "order" )
                origIndex = index
                while int( index ) in nodes:
                    index = int( index )
                    index += 1
                    index = str( index )
            else:
                self.indexCounter -= 1
                index = str( self.indexCounter )
                origIndex = "-"
                
            # Get label and icon
            label = root.find( "label" ).text
            
            icon = root.find( "icon" )
            if icon is not None:
                icon = icon.text
            else:
                icon = ""
            
            # Add it to our list of nodes
            if isFolder:
                nodes[ int( index ) ] = [ label, icon, urllib.quote( origFolder.decode( "utf-8" ) ), "folder", origIndex ]
            else:
                nodes[ int( index ) ] = [ label, icon, file, "item", origIndex ]
        except:
            print_exc()
            
    def getViewElement( self, file, element, newvalue ):
        try:
            # Load the file
            tree = xmltree.parse( file )
            root = tree.getroot()
            
            # Change the element
            node = root.find( element )
            if node is not None:
                return node.text
            else:
                return ""
        except:
            print_exc()
            
    def changeViewElement( self, file, element, newvalue ):
        try:
            # Load the file
            tree = xmltree.parse( file )
            root = tree.getroot()
            
            # If the element is content, we can only delete this if there are no
            # rules, limits, orders
            if element == "content":
                rule = root.find( "rule" )
                order = root.find( "order" )
                limit = root.find( "limit" )
                if rule is not None or order is not None or limit is not None:
                    xbmcgui.Dialog().ok( __addonname__, __language__( 30404 ) )
                    return
            
            # Find the element
            node = root.find( element )
            
            if node is not None:
                # If we've been passed an empty value, delete the node
                if newvalue == "":
                    root.remove( node )
                else:
                    node.text = newvalue
            else:
                # Add a new node
                if newvalue != "":
                    xmltree.SubElement( root, element ).text = newvalue
            
            # Pretty print and save
            self.indent( root )
            tree.write( file, encoding="UTF-8" )
        except:
            print_exc()
            
    def getRootAttrib( self, file, attrib ):
        try:
            # Load the file
            tree = xmltree.parse( file )
            root = tree.getroot()
            
            # Find the element
            if attrib in root.attrib:
                return root.attrib.get( attrib )
            else:
                return ""
        except:
            print_exc()
            
    def changeRootAttrib( self, file, attrib, newvalue ):
        try:
            # Load the file
            tree = xmltree.parse( file )
            root = tree.getroot()
            
            # If empty newvalue, delete the attribute
            if newvalue == "":
                if attrib in root.attrib:
                    root.attrib.pop( attrib )
            else:
                # Change or add the attribute
                root.set( attrib, newvalue )
            
            # Pretty print and save
            self.indent( root )
            tree.write( file, encoding="UTF-8" )
        except:
            print_exc()
            
    def copyNode(self, dirs, files, target, origin):
        for file in files:
            xbmcvfs.copy( os.path.join( origin, file ), os.path.join( target, file ) )
            
        for dir in dirs:
            nextDirs, nextFiles = xbmcvfs.listdir( os.path.join( origin, dir ) )
            self.copyNode( nextDirs, nextFiles, os.path.join( target, dir ), os.path.join( origin, dir ) )
            
    # in-place prettyprint formatter
    def indent( self, elem, level=0 ):
        i = "\n" + level*"\t"
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "\t"
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                self.indent(elem, level+1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i
                
    # Slugify functions
    def smart_truncate(string, max_length=0, word_boundaries=False, separator=' '):
        string = string.strip(separator)

        if not max_length:
            return string

        if len(string) < max_length:
            return string

        if not word_boundaries:
            return string[:max_length].strip(separator)

        if separator not in string:
            return string[:max_length]

        truncated = ''
        for word in string.split(separator):
            if word:
                next_len = len(truncated) + len(word) + len(separator)
                if next_len <= max_length:
                    truncated += '{0}{1}'.format(word, separator)
        if not truncated:
            truncated = string[:max_length]
        return truncated.strip(separator)

    def slugify(self, text, entities=True, decimal=True, hexadecimal=True, max_length=0, word_boundary=False, separator='-', convertInteger=False):
        # Handle integers
        if convertInteger and text.isdigit():
            text = "NUM-" + text
    
        # text to unicode
        if type(text) != types.UnicodeType:
            text = unicode(text, 'utf-8', 'ignore')

        # decode unicode ( ??? = Ying Shi Ma)
        text = unidecode(text)

        # text back to unicode
        if type(text) != types.UnicodeType:
            text = unicode(text, 'utf-8', 'ignore')

        # character entity reference
        if entities:
            text = CHAR_ENTITY_REXP.sub(lambda m: unichr(name2codepoint[m.group(1)]), text)

        # decimal character reference
        if decimal:
            try:
                text = DECIMAL_REXP.sub(lambda m: unichr(int(m.group(1))), text)
            except:
                pass

        # hexadecimal character reference
        if hexadecimal:
            try:
                text = HEX_REXP.sub(lambda m: unichr(int(m.group(1), 16)), text)
            except:
                pass

        # translate
        text = unicodedata.normalize('NFKD', text)
        if sys.version_info < (3,):
            text = text.encode('ascii', 'ignore')

        # replace unwanted characters
        text = REPLACE1_REXP.sub('', text.lower()) # replace ' with nothing instead with -
        text = REPLACE2_REXP.sub('-', text.lower())

        # remove redundant -
        text = REMOVE_REXP.sub('-', text).strip('-')

        # smart truncate if requested
        if max_length > 0:
            text = smart_truncate(text, max_length, word_boundary, '-')

        if separator != '-':
            text = text.replace('-', separator)

        return text
                

if ( __name__ == "__main__" ):
    log('script version %s started' % __addonversion__)
    
    # Profiling
    #filename = os.path.join( __datapath__, strftime( "%Y%m%d%H%M%S",gmtime() ) + "-" + str( random.randrange(0,100000) ) + ".log" )
    #cProfile.run( 'Main()', filename )
    
    #stream = open( filename + ".txt", 'w')
    #p = pstats.Stats( filename, stream = stream )
    #p.sort_stats( "cumulative" )
    #p.print_stats()
    
    # No profiling
    Main()
    
    log('script stopped')
