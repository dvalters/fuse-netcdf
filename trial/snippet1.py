    def _full_path(self, partial, useFallBack=False):
        if partial.startswith("/"):
            partial = partial[1:]

        # Find out the real path. If has been requesetd for a fallback path,
        # use it
        path = primaryPath = os.path.join(
            self.fallbackPath if useFallBack else self.root, partial)

        # If the pah does not exists and we haven't been asked for the fallback path
        # try to look on the fallback filessytem
        if not os.path.exists(primaryPath) and not useFallBack:
            path = fallbackPath = os.path.join(self.fallbackPath, partial)

            # If the path does not exists neither in the fallback fielsysem
            # it's likely to be a write operation, so use the primary
            # filesystem... unless the path to get the file exists in the
            # fallbackFS!
            if not os.path.exists(fallbackPath):
                # This is probabily a write operation, so prefer to use the
                # primary path either if the directory of the path exists in the
                # primary FS or not exists in the fallback FS

                primaryDir = os.path.dirname(primaryPath)
                fallbackDir = os.path.dirname(fallbackPath)

                if os.path.exists(primaryDir) or not os.path.exists(fallbackDir):
                    path = primaryPath

        return path

