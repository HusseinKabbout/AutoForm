# -*- coding: utf-8 -*-
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    copyright            : (C) 2017 by William Habelt / Sourcepole AG
#    email                : wha@sourcepole.ch


from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsCredentials

import psycopg2


class Connector:
    """
    Establishes a connection to the database of a layer, based on its uri.
    """

    def __init__(self, iface):
        self.iface = iface

    def uriDatabaseConnect(self, uri):
        """Create a connection from a uri and return a cursor of it."""
        conninfo = uri.connectionInfo()
        conn = None
        cur = None
        ok = False
        while not conn:
            try:
                conn = psycopg2.connect(uri.connectionInfo())
                cur = conn.cursor()
            except psycopg2.OperationalError as e:
                (ok, user, passwd) = QgsCredentials.instance().get(
                    conninfo, uri.username(), uri.password())
                if not ok:
                    break

        if not conn:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Connection Error",
                "Could not connect to PostgreSQL database -"
                "check connection info")

        if ok:
            QgsCredentials.instance().put(conninfo, user, passwd)

        return cur
