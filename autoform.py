# -*- coding: utf-8 -*-
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    copyright            : (C) 2017 by William Habelt / Sourcepole AG
#    email                : wha@sourcepole.ch

from qgis.PyQt.QtWidgets import QAction
from qgis.core import (Qgis, QgsDataSourceUri, QgsProject, QgsVectorLayer,
                       QgsLayerTreeGroup)
from qgis.gui import QgsEditorWidgetRegistry
from .connector import Connector
from .relationretriever import RelationRetriever


class AutoForm:
    """The main class of the plugin

    The AutoForm class controls the flow of the plugin and makes sure that all
    of the functions are called in the correct order. It relies on the
    Connector class to create a connection to the database and the
    RelationRetriever class for performing the queries on the database. The
    functions responsible for directly altering the feature form may be found
    here.
    """

    def __init__(self, iface):
        self.iface = iface
        self.connector = Connector(iface)

    def initGui(self):
        self.action = QAction("Generate Form", self.iface.mainWindow())
        self.iface.addPluginToMenu("AutoForm", self.action)
        self.action.triggered.connect(self.handleFormofLayer)

    def unload(self):
        self.iface.removePluginMenu("AutoForm", self.action)

    def handleFormofLayer(self):
        """Calls all important functions in the plugin.

        First, if the selected layer is valid, the plugin checks whether it has
        any foreign keys which reference another table. If this is the case
        then those tables are loaded into the project and a ValueRelation
        widget type is created in the appropriate field. Then, all other fields
        have their widgets altered based on their fieldType and length. Next,
        all empty groups are removed from the MapLayerRegistry. This is in case
        the plugin added an empty group for the referenced tables but none were
        added.
        """
        selected_layer = self.iface.activeLayer()
        if selected_layer:
            if selected_layer.dataProvider().name() != 'postgres':
                self.iface.messageBar().pushMessage(
                    "Autoform",
                    "Please select a PostGIS layer before running the plugin.",
                    level=Qgis.MessageLevel(1))
                return
            self.identifyRelations(selected_layer)
            self.alterForm(selected_layer)
            self.filterEmptyGroups()
            self.iface.messageBar().pushMessage(
                "Autoform",
                "Form widgets were successfully changed!.",
                level=Qgis.MessageLevel(0))
        else:
            self.iface.messageBar().pushMessage(
                "Autoform",
                "Please select a PostGIS layer before running the plugin.",
                level=Qgis.MessageLevel(2))

    def alterForm(self, selected_layer):
        """
        Iterate over the fields of the layer and alters the widgets in
        accordance to the typeName and length.
        """
        not_nullable_columns = self.checkNullableColumns(selected_layer)

        for field_index, field in enumerate(selected_layer.fields()):
            f_type = field.typeName()

            widget_type = QgsEditorWidgetRegistry().findBest(
                selected_layer, field.displayName())
            widget_type_name = QgsEditorWidgetRegistry().findBest(
                selected_layer, field.displayName()).type()

            if widget_type_name != 'TextEdit':
                pass
            elif f_type == "text":
                selected_layer.setEditorWidgetSetup(field_index, widget_type)
                selected_layer.editFormConfig().setWidgetConfig(
                    field.displayName(), {
                        'IsMultiline': True, 'UseHtml': False})
            elif f_type == "varchar":
                selected_layer.setEditorWidgetSetup(field_index, widget_type)
                selected_layer.editFormConfig().setWidgetConfig(
                    field.displayName(), {
                        'IsMultiline': (field.length() > 80),
                        'UseHtml': False})
            elif f_type == "date":
                selected_layer.setEditorWidgetSetup(field_index, widget_type)
                selected_layer.editFormConfig().setWidgetConfig(
                    field.displayName(), {
                        'display_format': 'yyyy-MM-dd',
                        'field_format': 'yyyy-MM-dd', 'calendar_popup': True})
            elif f_type == "bool":
                selected_layer.setEditorWidgetSetup(field_index, widget_type)
                selected_layer.editFormConfig().setWidgetConfig(
                    field.displayName(), {
                        'CheckedState': 't', 'UncheckedState': 'f'})

            selected_layer.setFieldConstraint(
                field_index,
                not_nullable_columns[field_index])

    def handleValueRelations(self, new_layer, ref_native_col_num,
                             ref_foreign_col_num, selected_layer):
        """
        Create a ValueRelation widget from the field numbers for the
        selected layer
        """
        fields = new_layer.fields()
        foreign_column = fields[ref_foreign_col_num - 1].name()

        fields = selected_layer.fields()
        native_column = fields[ref_native_col_num - 1].name()

        if native_column and foreign_column:
            column_index = ref_native_col_num - 1
            new_layer_id = new_layer.id()

            widget_type = QgsEditorWidgetRegistry().findBest(
                selected_layer, column_index.displayName())

            selected_layer.setEditorWidgetSetup(column_index, widget_type)
            selected_layer.editFormConfig().setWidgetConfig(
                column_index,
                {'Layer': new_layer_id, 'Key': foreign_column,
                 'Value': foreign_column, "AllowMulti": False,
                 "AllowNull": False, "OrderByValue": True})
            # Repeat the entire process for the layer which was just added
            self.identifyRelations(new_layer)
            self.alterForm(new_layer)

    def identifyRelations(self, selected_layer):
        """Return a cursor of the connection based on the layer's uri."""
        data = selected_layer.dataProvider()
        if data.name() != 'postgres':
            return
        uri = QgsDataSourceUri(data.dataSourceUri())
        cur = self.connector.uriDatabaseConnect(uri)

        if cur is False:
            return

        self.handleLayers(cur, uri, selected_layer)

    def handleLayers(self, cur, uri, selected_layer):
        """Decides which variables to use for a ValueRelation in a table if applicable.

        First, it creates an instance of the RelationRetriever class, which it
        then uses to retrieve a list of layer id's. Secondly, a group is
        created for the layers which will be automatically loaded. Next, a for
        loop begins to iterate over every table oid which was previously
        retrieved and a layer variable is set for the RelationRetriever class.
        Then, for each table it's primary key and the relevant field numbers of
        the foreign key relation are retrieved. Finally, the information is
        used to create a new layer by the addRefTables function, which goes on
        to be used in the handleValueRelations function.
        """
        relationretriever = RelationRetriever(cur)
        referenced_layers = relationretriever.retrieveReferencedTables(uri)
        root = QgsProject.instance().layerTreeRoot()
        tableGroup = root.findGroup("Tables")

        if not tableGroup:
            tableGroup = root.addGroup("Tables")

        for a_layer in referenced_layers:
            relationretriever.setLayer(a_layer[0])
            foreign_tables = relationretriever.retrieveForeignTables()

            for a_table in foreign_tables:
                pkeyName = relationretriever.retrieveTablePrimaryKeyName()
                ref_foreign_col_num = relationretriever.retrieveForeignCol(uri)
                ref_native_col_num = relationretriever.retrieveNativeCol(uri)
                new_layer = self.addRefTables(uri, a_table[0], pkeyName,
                                              tableGroup)

                if new_layer is not False:
                    self.handleValueRelations(new_layer, ref_native_col_num,
                                              ref_foreign_col_num,
                                              selected_layer)

    def addRefTables(self, uri, table, attr_name, tableGroup):
        """
        Create a datasource for a referenced layer and add it to the map
        layer registry.
        """
        foreign_uri = QgsDataSourceUri()
        foreign_uri.setConnection(uri.host(), uri.port(), uri.database(),
                                  uri.username(), uri.password())
        foreign_uri.setDataSource(uri.schema(), table, None, "", attr_name)
        new_layer = QgsVectorLayer(foreign_uri.uri(), table, "postgres")

        if new_layer.isValid():
            layer_exists = False

            for layers in QgsProject().mapLayers().values():
                layer_data = layers.dataProvider()
                if foreign_uri.uri() == layer_data.dataSourceUri():
                    layer_exists = True

            if not layer_exists:
                QgsProject.addMapLayer(new_layer, False)
                tableGroup.addLayer(new_layer)
                return new_layer
            else:
                return False

    def filterEmptyGroups(self):
        """Delete any groups without children."""
        root = QgsProject.instance().layerTreeRoot()

        for child in root.children():
            if isinstance(child, QgsLayerTreeGroup):
                if not child.findLayers():
                    root.removeChildNode(child)

    def checkNullableColumns(self, selected_layer):
        """
        Run query to check for columns that allow NULL-values
        (postgres provider)
        """
        data = selected_layer.dataProvider()
        if data.name() == 'postgres':
            uri = QgsDataSourceUri(data.dataSourceUri())
            cur = self.connector.uriDatabaseConnect(uri)
            relationretriever = RelationRetriever(cur)
            # List of columns with the NOT NULL modifier
            not_nullable_columns = relationretriever.checkNotNull(uri)
            return not_nullable_columns
