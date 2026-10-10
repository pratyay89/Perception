"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { QPCard, isFullyEvaluated } from "./qp-card";
import { api, errorMessage } from "@/lib/api";
import { clearSession } from "@/lib/auth";
import { getInitials, STATUS_LABEL } from "@/lib/format";
import type {
  AssociatedUser,
  AssociationsResponse,
  PaperSummary,
} from "@/lib/types";
import { motion, AnimatePresence } from "framer-motion";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetFooter,
} from "@/components/ui/sheet";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

import {
  Plus,
  LogOut,
  User,
  Search,
  BookOpen,
  FileText,
  CheckSquare,
  Clock,
  Delete,
  RefreshCw,
  ChevronRight,
  List,
  Grid,
  Trophy,
} from "lucide-react";

import { toast } from "sonner";
import { GraphSearchCanvas } from "@/components/graph-search-canvas";
import { ThemeToggle } from "@/components/theme-toggle";

type Paper = PaperSummary;

interface TeacherViewProps {
  email: string;
}

export function TeacherDashboard({ email }: TeacherViewProps) {
  const router = useRouter();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [students, setStudents] = useState<AssociatedUser[]>([]);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedTab, setSelectedTab] = useState<string>("all");
  const [addStudentQuery, setAddStudentQuery] = useState<string>("");
  const [addingStudent, setAddingStudent] = useState<boolean>(false);

  // "Ongoing" papers are visible to students: open now, or scheduled to open.
  const isOngoing = (paper: Paper) =>
    paper.status === "open" || paper.status === "scheduled";
  const isExpired = (paper: Paper) => paper.status === "closed";

  const ongoingPapers = papers.filter(isOngoing);
  const evaluatedPapers = papers.filter(isFullyEvaluated);

  const filteredPapers = papers.filter((paper) => {
    const matchesSearch = paper.title
      .toLowerCase()
      .includes(searchQuery.toLowerCase());

    if (selectedTab === "all") return matchesSearch;
    if (selectedTab === "ongoing") return isOngoing(paper) && matchesSearch;
    if (selectedTab === "drafts")
      return paper.status === "draft" && matchesSearch;
    if (selectedTab === "expired") return isExpired(paper) && matchesSearch;
    if (selectedTab === "evaluated")
      return isFullyEvaluated(paper) && matchesSearch;

    return matchesSearch;
  });

  const fetchPapers = async () => {
    try {
      const response = await api.get<Paper[]>("/papers");
      setPapers(response.data);
    } catch (error) {
      toast.error(errorMessage(error, "Failed to fetch papers"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const getStudents = async () => {
    try {
      const response = await api.get<AssociationsResponse>(
        "/auth/associations"
      );
      setStudents(response.data.users);
    } catch (error) {
      toast.error(errorMessage(error, "Failed to fetch students"));
    }
  };

  const handleRemoveStudent = async (studentEmail: string) => {
    try {
      await api.delete("/auth/associations", {
        params: { s_email: studentEmail },
      });
      toast.success("Student removed successfully");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to remove student"));
    } finally {
      getStudents();
    }
  };

  const handleAddStudent = async () => {
    const studentEmail = addStudentQuery.trim();
    if (!studentEmail) {
      toast.error("Enter the student's email address");
      return;
    }

    setAddingStudent(true);
    try {
      await api.post("/auth/associations", null, {
        params: { s_email: studentEmail },
      });
      toast.success("Student added successfully");
      setAddStudentQuery("");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to add student"));
    } finally {
      setAddingStudent(false);
      getStudents();
    }
  };

  const refreshData = async () => {
    setRefreshing(true);
    await Promise.all([fetchPapers(), getStudents()]);
  };

  useEffect(() => {
    fetchPapers();
    getStudents();
  }, [email]);

  const handleLogout = () => {
    clearSession();
    router.push("/login");
  };

  const handleCreatePaper = () => {
    router.push("/create-paper");
  };

  return (
    <div className="relative isolate min-h-screen bg-background">
      <div className="fixed inset-0 -z-10">
        <GraphSearchCanvas variant="subtle" />
      </div>
      {/* Header */}
      <header className="bg-card border-b border-border sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-4">
              <div className="rounded-lg overflow-hidden flex items-center justify-center bg-primary/10 h-10 w-10">
                <BookOpen className="h-5 w-5 text-primary" />
              </div>
              <h1 className="text-xl font-bold text-foreground hidden md:block">
                Teacher Dashboard
              </h1>
            </div>

            <div className="flex items-center gap-3 md:gap-4">
              <div className="relative rounded-md max-w-xs hidden md:block">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-4 w-4 text-muted-foreground/70" />
                </div>
                <Input
                  placeholder="Search papers..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 h-9 focus-visible:ring-primary"
                />
              </div>
              <Button
                onClick={refreshData}
                variant="ghost"
                size="icon"
                className={`${refreshing ? "animate-spin" : ""}`}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button
                onClick={handleCreatePaper}
                className="flex items-center gap-2 bg-primary hover:bg-primary/90 shadow-sm"
                size="sm"
              >
                <Plus className="h-4 w-4" />
                <span className="hidden sm:inline">Create</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={() => router.push("/leaderboard")}
              >
                <Trophy className="h-4 w-4" />
                <span className="hidden sm:inline">Leaderboard</span>
              </Button>
              <ThemeToggle />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-full h-9 w-9"
                  >
                    <Avatar className="h-9 w-9 bg-primary/10 hover:bg-primary/20 transition-colors">
                      <AvatarFallback className="text-sm text-primary">
                        {getInitials(email)}
                      </AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium">My Account</p>
                      <p className="text-xs text-muted-foreground truncate">{email}</p>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <Sheet>
                    <SheetTrigger asChild onClick={getStudents}>
                      <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                        <User className="h-4 w-4 mr-2" />
                        <span>Manage Students</span>
                        <ChevronRight className="h-4 w-4 ml-auto" />
                      </DropdownMenuItem>
                    </SheetTrigger>
                    <SheetContent
                      side="right"
                      className="w-[400px] sm:w-[540px]"
                    >
                      <SheetHeader>
                        <SheetTitle>Student Management</SheetTitle>
                        <SheetDescription>
                          View and manage students in your class
                        </SheetDescription>
                      </SheetHeader>
                      <div className="mt-6 space-y-6">
                        <div className="flex items-center gap-2">
                          <div className="relative flex-1">
                            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                            <Input
                              type="email"
                              placeholder="Student's email address"
                              className="pl-9"
                              value={addStudentQuery}
                              onChange={(e) =>
                                setAddStudentQuery(e.target.value)
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter") handleAddStudent();
                              }}
                            />
                          </div>
                          <Button
                            variant="default"
                            onClick={handleAddStudent}
                            disabled={addingStudent}
                          >
                            {addingStudent ? "Adding..." : "Add Student"}
                          </Button>
                        </div>

                        {/* Students List */}
                        <Card>
                          <CardContent className="p-0">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Student</TableHead>
                                  <TableHead className="w-[100px] text-right">
                                    Actions
                                  </TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {students.length > 0 ? (
                                  students.map((student) => (
                                    <TableRow key={student.email}>
                                      <TableCell className="flex items-center gap-2">
                                        <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
                                          {getInitials(student.email)}
                                        </div>
                                        <div>
                                          <p className="text-sm font-medium">
                                            {student.full_name}
                                          </p>
                                          <p className="text-xs text-muted-foreground">
                                            {student.email}
                                          </p>
                                        </div>
                                      </TableCell>
                                      <TableCell className="text-right">
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          aria-label={`Remove ${student.email}`}
                                          onClick={() =>
                                            handleRemoveStudent(student.email)
                                          }
                                        >
                                          <Delete className="h-4 w-4" />
                                        </Button>
                                      </TableCell>
                                    </TableRow>
                                  ))
                                ) : (
                                  <TableRow>
                                    <TableCell colSpan={2}>
                                      <div className="text-center py-6 text-sm text-muted-foreground">
                                        <p>No students found</p>
                                        <p className="text-xs mt-1">
                                          Add a student by the email they
                                          signed up with
                                        </p>
                                      </div>
                                    </TableCell>
                                  </TableRow>
                                )}
                              </TableBody>
                            </Table>
                          </CardContent>
                        </Card>
                      </div>
                      <SheetFooter className="mt-4">
                        <div className="text-xs text-muted-foreground">
                          Students can view and attempt your assessments
                        </div>
                      </SheetFooter>
                    </SheetContent>
                  </Sheet>
                  <DropdownMenuItem
                    onClick={handleLogout}
                    className="text-red-600"
                  >
                    <LogOut className="h-4 w-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Dashboard Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <Card className="bg-card">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground font-medium">
                  Total Papers
                </p>
                <p className="text-2xl font-bold">{papers.length}</p>
              </div>
              <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                <FileText className="h-6 w-6 text-primary" />
              </div>
            </CardContent>
          </Card>

          {/* Active Count */}
          <Card className="bg-card">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground font-medium">
                  Active Papers
                </p>
                <p className="text-2xl font-bold">{ongoingPapers.length}</p>
              </div>
              <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                <Clock className="h-6 w-6 text-green-600" />
              </div>
            </CardContent>
          </Card>

          {/* Evaluated Count */}
          <Card className="bg-card">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground font-medium">Evaluated</p>
                <p className="text-2xl font-bold">{evaluatedPapers.length}</p>
              </div>
              <div className="h-12 w-12 rounded-full bg-blue-100 flex items-center justify-center">
                <CheckSquare className="h-6 w-6 text-blue-600" />
              </div>
            </CardContent>
          </Card>

          {/* Students Count */}
          <Card className="bg-card">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground font-medium">Students</p>
                <p className="text-2xl font-bold">{students.length}</p>
              </div>
              <div className="h-12 w-12 rounded-full bg-amber-100 flex items-center justify-center">
                <User className="h-6 w-6 text-amber-600" />
              </div>
            </CardContent>
          </Card>
        </div>

        {loading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
            </div>
          </div>
        ) : papers.length === 0 ? (
          <Card className="border-dashed border-2 p-12 flex flex-col items-center justify-center text-center">
            <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
              <FileText className="h-8 w-8 text-primary" />
            </div>
            <h3 className="text-lg font-semibold text-foreground mb-1">
              No assessments created yet
            </h3>
            <p className="text-muted-foreground mb-6 max-w-md">
              Create your first assessment to start evaluating your students&apos;
              understanding.
            </p>
            <Button
              onClick={handleCreatePaper}
              className="flex items-center gap-2"
            >
              <Plus className="h-4 w-4" />
              Create First Assessment
            </Button>
          </Card>
        ) : (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <Tabs
                defaultValue="all"
                className="w-full sm:w-auto"
                value={selectedTab}
                onValueChange={setSelectedTab}
              >
                <TabsList>
                  <TabsTrigger value="all">All Papers</TabsTrigger>
                  <TabsTrigger value="ongoing">Ongoing</TabsTrigger>
                  <TabsTrigger value="drafts">Drafts</TabsTrigger>
                  <TabsTrigger value="expired">Expired</TabsTrigger>
                  <TabsTrigger value="evaluated">Evaluated</TabsTrigger>
                </TabsList>
              </Tabs>

              <div className="flex items-center justify-between sm:justify-end gap-2">
                <div className="relative w-full sm:w-auto md:hidden">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search papers..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 h-9 w-full"
                  />
                </div>
                <div className="flex items-center border rounded-md overflow-hidden">
                  <Button
                    variant={viewMode === "grid" ? "default" : "ghost"}
                    size="icon"
                    className="rounded-none h-9 w-9"
                    onClick={() => setViewMode("grid")}
                  >
                    <Grid className="h-4 w-4" />
                  </Button>
                  <Button
                    variant={viewMode === "list" ? "default" : "ghost"}
                    size="icon"
                    className="rounded-none h-9 w-9"
                    onClick={() => setViewMode("list")}
                  >
                    <List className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>

            {filteredPapers.length === 0 ? (
              <div className="text-center py-12 bg-card rounded-lg border">
                <div className="h-12 w-12 rounded-full bg-muted mx-auto flex items-center justify-center mb-3">
                  <Search className="h-6 w-6 text-muted-foreground/70" />
                </div>
                <h3 className="text-sm font-semibold text-foreground mb-1">
                  No matching assessments
                </h3>
                <p className="text-sm text-muted-foreground">
                  Try adjusting your search or filter criteria
                </p>
              </div>
            ) : viewMode === "grid" ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <AnimatePresence>
                  {filteredPapers.map((paper) => (
                    <motion.div
                      key={paper.qpid}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.2 }}
                    >
                      <QPCard
                        paper={paper}
                        user_type="teacher"
                        onChanged={fetchPapers}
                      />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            ) : (
              <Card>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredPapers.map((paper) => (
                      <TableRow
                        key={paper.qpid}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => router.push(`/view-paper/${paper.qpid}`)}
                      >
                        <TableCell className="font-medium">
                          {paper.title}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Badge
                              variant={
                                isExpired(paper) ? "destructive" : "outline"
                              }
                            >
                              {isExpired(paper)
                                ? "Expired"
                                : STATUS_LABEL[paper.status]}
                            </Badge>
                            {isFullyEvaluated(paper) && (
                              <Badge variant="secondary">Evaluated</Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" className="h-8">
                            View
                            <ChevronRight className="ml-1 h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
